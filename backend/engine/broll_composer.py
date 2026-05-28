# -*- coding: utf-8 -*-
"""字幕驱动 B-roll 视频合成器。"""

import json
import logging
import math
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.config.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class BrollComposer:
    """负责按字幕镜头计划裁剪、拼接 B-roll，并保留原始音轨。"""

    def __init__(self, ffmpeg_path: str = ''):
        self.ffmpeg_path = ffmpeg_path or shutil.which('ffmpeg') or 'ffmpeg'
        self.ffprobe_path = shutil.which('ffprobe') or 'ffprobe'
        self.output_dir = PROJECT_ROOT / 'output' / 'broll'
        self.work_dir = PROJECT_ROOT / 'temp' / 'broll'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def compose(
        self,
        project_id: str,
        source_video_path: str,
        shots: List[Dict],
        subtitles: Optional[List[Dict]] = None,
        style: Optional[Dict] = None,
        config: Optional[Dict] = None,
        progress_callback=None
    ) -> Dict:
        """合成 B-roll 视频。"""
        config = config or {}
        subtitles = subtitles or []
        style = style or {}
        source_path = self._resolve_path(source_video_path)
        if not source_path or not source_path.exists():
            raise FileNotFoundError('原视频文件不存在，无法合成补画面')

        video_info = self.get_video_info(source_path)
        source_duration = max(0.1, float(video_info.get('duration') or 0.0))
        target_width, target_height = self._target_size(video_info, config.get('aspect_ratio') or 'original')
        fps = int(float(video_info.get('fps') or 25) or 25)
        fps = max(15, min(fps, 30))

        run_id = f'{project_id}_{uuid.uuid4().hex[:8]}'
        run_dir = self.work_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        timeline = self._build_timeline(shots, source_duration)
        if not timeline:
            raise RuntimeError('没有可合成的镜头计划')

        segments = []
        for index, item in enumerate(timeline, start=1):
            if progress_callback:
                progress_callback(10 + int(index / max(1, len(timeline)) * 55), f'正在生成镜头片段 {index}/{len(timeline)}')
            segment_path = run_dir / f'segment_{index:04d}.mp4'
            self._render_segment(
                item=item,
                source_path=source_path,
                output_path=segment_path,
                target_width=target_width,
                target_height=target_height,
                fps=fps
            )
            segments.append(segment_path)

        if progress_callback:
            progress_callback(70, '正在拼接镜头片段')
        concat_path = run_dir / 'concat_list.txt'
        concat_video = run_dir / 'broll_silent.mp4'
        self._write_concat_list(concat_path, segments)
        self._run([
            self.ffmpeg_path, '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_path),
            '-c', 'copy',
            str(concat_video)
        ], timeout=1800)

        if progress_callback:
            progress_callback(80, '正在合并原始配音音轨')
        with_audio = run_dir / 'broll_with_audio.mp4'
        self._run([
            self.ffmpeg_path, '-y',
            '-i', str(concat_video),
            '-i', str(source_path),
            '-map', '0:v:0',
            '-map', '1:a?',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',
            '-movflags', '+faststart',
            str(with_audio)
        ], timeout=1800)

        final_path = self.output_dir / f'broll_{run_id}.mp4'
        if (config.get('subtitle_mode') or 'burned') == 'burned' and subtitles:
            if progress_callback:
                progress_callback(90, '正在烧录字幕')
            try:
                ass_path = run_dir / 'subtitles.ass'
                ass_path.write_text(self._build_ass_content(subtitles, style), encoding='utf-8')
                self._burn_subtitles(with_audio, ass_path, final_path)
            except Exception as e:
                logger.warning(f'B-roll 字幕烧录失败，输出无字幕版本: {e}')
                shutil.copyfile(with_audio, final_path)
        else:
            shutil.copyfile(with_audio, final_path)

        if progress_callback:
            progress_callback(100, '补画面视频合成完成')

        rel_url = f'/output/broll/{final_path.name}'
        return {
            'output_path': str(final_path),
            'output_url': rel_url,
            'duration': self.get_video_info(final_path).get('duration') or source_duration,
            'width': target_width,
            'height': target_height
        }

    def get_video_info(self, path: Path) -> Dict:
        """读取视频基础信息。"""
        proc = self._run([
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(path)
        ], timeout=30, check=False)
        if proc.returncode != 0:
            return {}
        try:
            data = json.loads(proc.stdout or '{}')
        except Exception:
            return {}
        video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), {})
        fps = 25.0
        try:
            rate = str(video_stream.get('r_frame_rate') or '25/1')
            if '/' in rate:
                numerator, denominator = rate.split('/', 1)
                fps = float(numerator) / max(1.0, float(denominator))
            else:
                fps = float(rate)
        except Exception:
            fps = 25.0
        return {
            'duration': float((data.get('format') or {}).get('duration') or 0.0),
            'width': int(video_stream.get('width') or 1280),
            'height': int(video_stream.get('height') or 720),
            'fps': fps
        }

    def _build_timeline(self, shots: List[Dict], source_duration: float) -> List[Dict]:
        normalized = []
        for shot in sorted(shots or [], key=lambda item: float(item.get('start') or 0)):
            start = max(0.0, float(shot.get('start') or 0.0))
            end = min(source_duration, max(start + 0.1, float(shot.get('end') or 0.0)))
            if end <= start:
                continue
            normalized.append(dict(shot, start=start, end=end, duration=end - start))

        timeline = []
        cursor = 0.0
        for shot in normalized:
            if shot['start'] > cursor + 0.05:
                timeline.append({'kind': 'source', 'start': cursor, 'end': shot['start'], 'duration': shot['start'] - cursor})
            timeline.append(dict(shot, kind='broll'))
            cursor = max(cursor, shot['end'])

        if cursor < source_duration - 0.05:
            timeline.append({'kind': 'source', 'start': cursor, 'end': source_duration, 'duration': source_duration - cursor})
        return timeline

    def _render_segment(
        self,
        item: Dict,
        source_path: Path,
        output_path: Path,
        target_width: int,
        target_height: int,
        fps: int
    ):
        duration = max(0.1, float(item.get('duration') or 0.1))
        candidate_path = self._selected_candidate_path(item)
        use_source = item.get('kind') == 'source' or not candidate_path or not candidate_path.exists() or bool(item.get('skipped'))

        vf = (
            f'scale={target_width}:{target_height}:force_original_aspect_ratio=increase,'
            f'crop={target_width}:{target_height},setsar=1,fps={fps},format=yuv420p'
        )
        if use_source:
            cmd = [
                self.ffmpeg_path, '-y',
                '-ss', str(max(0.0, float(item.get('start') or 0.0))),
                '-i', str(source_path),
                '-t', str(duration),
                '-an',
                '-vf', vf,
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '20',
                str(output_path)
            ]
        else:
            cmd = [
                self.ffmpeg_path, '-y',
                '-stream_loop', '-1',
                '-i', str(candidate_path),
                '-t', str(duration),
                '-an',
                '-vf', vf,
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '20',
                str(output_path)
            ]
        self._run(cmd, timeout=max(120, int(duration * 20)))

    def _selected_candidate_path(self, shot: Dict) -> Optional[Path]:
        selected_id = shot.get('selected_candidate_id') or ''
        candidates = shot.get('candidates') or []
        selected = None
        if selected_id:
            selected = next((item for item in candidates if item.get('candidate_id') == selected_id), None)
        if not selected:
            selected = next((item for item in candidates if item.get('local_path')), None)
        if not selected:
            return None
        return self._resolve_path(selected.get('local_path'))

    def _target_size(self, info: Dict, aspect_ratio: str) -> Tuple[int, int]:
        width = int(info.get('width') or 1280)
        height = int(info.get('height') or 720)
        if (aspect_ratio or '').lower() in {'16:9', '16_9', 'landscape'}:
            return 1280, 720
        width = max(320, width)
        height = max(240, height)
        if width % 2:
            width -= 1
        if height % 2:
            height -= 1
        return width, height

    def _write_concat_list(self, path: Path, segments: List[Path]):
        lines = []
        for segment in segments:
            text = segment.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{text}'")
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def _burn_subtitles(self, video_path: Path, ass_path: Path, output_path: Path):
        escaped = self._escape_filter_path(ass_path)
        self._run([
            self.ffmpeg_path, '-y',
            '-i', str(video_path),
            '-vf', f"subtitles='{escaped}'",
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '20',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            str(output_path)
        ], timeout=1800)

    def _build_ass_content(self, subtitles: List[Dict], style: Dict) -> str:
        font = style.get('fontFamily') or style.get('font_family') or 'Microsoft YaHei'
        font_size = int(float(style.get('fontSize') or style.get('font_size') or 42))
        font_size = max(12, min(120, font_size))
        position = style.get('position') or 'bottom'
        alignment = {'bottom': 2, 'center': 5, 'top': 8}.get(position, 2)
        primary = self._hex_to_ass_color(style.get('fontColor') or style.get('font_color') or '#FFFFFF', '00')
        outline = self._hex_to_ass_color(style.get('bgColor') or style.get('bg_color') or '#000000', '00')
        back = self._hex_to_ass_color(style.get('bgColor') or style.get('bg_color') or '#000000', '80')
        bold = -1 if bool(style.get('bold', True)) else 0

        lines = [
            '[Script Info]',
            'ScriptType: v4.00+',
            'PlayResX: 1920',
            'PlayResY: 1080',
            'ScaledBorderAndShadow: yes',
            '',
            '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
            f'Style: Default,{font},{font_size},{primary},{primary},{outline},{back},{bold},0,0,0,100,100,0,0,3,3,0,{alignment},80,80,70,1',
            '',
            '[Events]',
            'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text'
        ]
        for item in subtitles:
            text = self._escape_ass_text(item.get('text') or '')
            if not text:
                continue
            lines.append(
                f'Dialogue: 0,{self._format_ass_time(item.get("start"))},'
                f'{self._format_ass_time(item.get("end"))},Default,,0,0,0,,{text}'
            )
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _format_ass_time(seconds) -> str:
        total = max(0.0, float(seconds or 0.0))
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        secs = int(total % 60)
        centis = int(math.floor((total - int(total)) * 100))
        return f'{hours}:{minutes:02d}:{secs:02d}.{centis:02d}'

    @staticmethod
    def _escape_ass_text(text: str) -> str:
        return str(text or '').replace('{', '(').replace('}', ')').replace('\r\n', '\n').replace('\n', r'\N').strip()

    @staticmethod
    def _hex_to_ass_color(value: str, alpha: str = '00') -> str:
        text = str(value or '#FFFFFF').strip().lstrip('#')
        if len(text) == 3:
            text = ''.join(ch + ch for ch in text)
        text = (text + 'FFFFFF')[:6]
        try:
            int(text, 16)
        except Exception:
            text = 'FFFFFF'
        return f'&H{alpha}{text[4:6]}{text[2:4]}{text[0:2]}'

    @staticmethod
    def _escape_filter_path(path: Path) -> str:
        text = str(path).replace('\\', '/')
        return text.replace(':', r'\:').replace("'", r"\'")

    @staticmethod
    def _resolve_path(path_value) -> Optional[Path]:
        if not path_value:
            return None
        path = Path(str(path_value))
        if path.is_absolute():
            return path
        return PROJECT_ROOT / str(path_value).lstrip('/\\')

    def _run(self, cmd: List[str], timeout: int = 600, check: bool = True):
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if check and proc.returncode != 0:
            logger.error(f'FFmpeg 命令失败: {proc.stderr[-1200:]}')
            raise RuntimeError('视频合成命令执行失败')
        return proc
