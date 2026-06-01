# -*- coding: utf-8 -*-
"""
字幕API - 完整实现
支持: 自动字幕生成、字幕编辑、字幕导出
"""

from flask import Blueprint, request, jsonify
import logging
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timedelta
import json
from pathlib import Path
from backend.config.paths import SUBTITLE_STYLES

BASE_DIR = Path(__file__).resolve().parents[2]

try:
    from backend.config.paths import FONTS_DIR, DEFAULT_FONT_NAME
except Exception:
    FONTS_DIR = BASE_DIR / 'backend' / 'assets' / 'fonts'
    DEFAULT_FONT_NAME = '微软雅黑'

subtitle_bp = Blueprint('subtitle', __name__)
logger = logging.getLogger(__name__)

STALE_ACTIVE_TASK_AGE = timedelta(hours=12)


@subtitle_bp.route('/api/subtitle/generate_legacy', methods=['POST'])
def generate_subtitle_legacy():
    """旧版字幕生成入口（已废弃）

    实际的自动字幕流程已经由主应用中的 /api/subtitle/generate 路由
    （frontend/app.py 内实现，调用 faster-whisper + ffmpeg）接管。

    为避免返回任何固定示例字幕，这里仅返回明确的错误提示，
    引导调用方迁移到新的实现。
    """
    logger.warning('收到对已废弃 /api/subtitle/generate 的调用，已提示使用新实现')
    return jsonify({
        'code': 1,
        'msg': '当前字幕生成已由主应用中的 /api/subtitle/generate 实现（faster-whisper），本旧版入口不再返回示例字幕，请在编辑器或项目流程中使用新的接口。',
        'data': None
    }), 410


def _resolve_material_path(path_value):
    """将数据库素材路径解析为本机可读取路径。"""
    if not path_value:
        return None

    path_text = str(path_value)
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate
    return BASE_DIR / path_text.lstrip('/\\')


def _format_segment(segment):
    try:
        return {
            'start': float(segment.start or 0),
            'end': float(segment.end or 0),
            'text': (segment.text or '').strip()
        }
    except Exception:
        return {
            'start': float(getattr(segment, 'start', 0.0) or 0.0),
            'end': float(getattr(segment, 'end', 0.0) or 0.0),
            'text': (getattr(segment, 'text', '') or '').strip()
        }


def _get_ffmpeg_executable():
    """获取可用的 FFmpeg 可执行文件路径。"""
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _json_safe_task_update(db_manager, task_id, status, progress=None, output_data=None, error_message=None):
    """统一更新任务状态，兼容不同数据库管理器实现。"""
    if db_manager is None:
        return
    try:
        if progress is not None and hasattr(db_manager, 'update_task_progress'):
            db_manager.update_task_progress(task_id, float(progress))
        if hasattr(db_manager, 'update_task_status'):
            db_manager.update_task_status(task_id, status, output_data=output_data, error_message=error_message)
    except Exception as e:
        logger.warning(f'字幕任务状态更新失败: {task_id}, {e}')


def _update_project_status(db_manager, project_id, status):
    """更新项目状态，失败不影响任务主流程。"""
    if not db_manager or not project_id or not hasattr(db_manager, 'update_project'):
        return
    try:
        db_manager.update_project(project_id, {'status': status})
    except Exception as e:
        logger.warning(f'项目状态更新失败: {project_id}, {status}, {e}')


def _parse_json_dict(value):
    """把数据库中的 JSON 字段安全解析成字典。"""
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_subtitle_items(raw_subtitles):
    """标准化用于持久化和恢复的字幕片段。"""
    subtitles = []
    if not isinstance(raw_subtitles, list):
        return subtitles
    for item in raw_subtitles:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        if not text:
            continue
        try:
            start = max(0.0, float(item.get('start') or 0.0))
            end = max(start + 0.1, float(item.get('end') or 0.0))
        except Exception:
            continue
        subtitles.append({'start': start, 'end': end, 'text': text})
    return subtitles


def _normalize_subtitle_style(raw_style):
    """标准化字幕样式，避免前端字段名差异导致恢复失败。"""
    style = raw_style if isinstance(raw_style, dict) else {}
    try:
        font_size = int(float(style.get('fontSize') or style.get('font_size') or 28))
    except Exception:
        font_size = 28
    font_size = max(14, min(72, font_size))
    return {
        'position': style.get('position') or 'bottom',
        'fontFamily': style.get('fontFamily') or style.get('font_family') or DEFAULT_FONT_NAME,
        'fontFile': style.get('fontFile') or style.get('font_file') or '',
        'fontSize': font_size,
        'fontColor': style.get('fontColor') or style.get('font_color') or '#ffffff',
        'bgColor': style.get('bgColor') or style.get('bg_color') or '#000000',
        'bold': bool(style.get('bold', True))
    }


def _get_project_result(project):
    """读取项目 result 字段。"""
    return _parse_json_dict((project or {}).get('result'))


def _get_saved_subtitle_session(project):
    """读取项目中保存的字幕编辑快照。"""
    result = _get_project_result(project)
    session = result.get('subtitle_session')
    return session if isinstance(session, dict) else {}


def _merge_subtitle_session(db_manager, project_id, updates):
    """合并保存字幕工具会话快照。"""
    if not db_manager or not project_id or not hasattr(db_manager, 'get_project'):
        return
    try:
        project = db_manager.get_project(project_id)
        if not project:
            return
        result = _get_project_result(project)
        session = result.get('subtitle_session')
        if not isinstance(session, dict):
            session = {}
        session.update(updates or {})
        session['updated_at'] = datetime.now().isoformat(timespec='seconds')
        result['subtitle_session'] = session
        db_manager.update_project(project_id, {'result': result})
    except Exception as e:
        logger.warning(f'保存字幕会话失败: {project_id}, {e}')


def _find_video_material(materials):
    """从素材列表中选一个可预览的视频素材。"""
    for material in materials or []:
        if material.get('type') == 'video' and material.get('path'):
            return material
    return None


def _latest_task(tasks, task_type=None, statuses=None):
    """按创建时间倒序任务列表中查找最新任务。"""
    status_set = set(statuses or [])
    for task in tasks or []:
        if task_type and task.get('type') != task_type:
            continue
        if status_set and task.get('status') not in status_set:
            continue
        return task
    return None


def _parse_datetime_value(value):
    """解析数据库返回的时间字段。"""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return None


def _is_recent_active_task(task):
    """判断 pending/running 任务是否仍值得前端恢复轮询。"""
    if not task or task.get('status') not in {'pending', 'running'}:
        return False
    last_time = (
        _parse_datetime_value(task.get('updated_at')) or
        _parse_datetime_value(task.get('started_at')) or
        _parse_datetime_value(task.get('created_at'))
    )
    if not last_time:
        return True
    return datetime.now() - last_time <= STALE_ACTIVE_TASK_AGE


def _task_output(task):
    """读取任务输出。"""
    return _parse_json_dict((task or {}).get('output_data'))


def _latest_completed_subtitles(db_manager, project_id, project=None):
    """从已完成的字幕任务中恢复最近一次有效字幕。"""
    try:
        tasks = (project or {}).get('tasks') or db_manager.get_tasks(project_id) or []
    except Exception:
        tasks = []
    completed_gen = _latest_task(tasks, 'subtitle_generate', ['completed'])
    if not completed_gen:
        return []
    return _normalize_subtitle_items(_task_output(completed_gen).get('subtitles') or [])


def _extract_audio_from_project(data, db_manager):
    """根据项目素材定位或提取可供 ASR 使用的音频。"""
    project_id = data.get('project_id')
    if not project_id:
        raise ValueError('缺少项目ID')
    if db_manager is None:
        raise RuntimeError('字幕生成服务未绑定数据库管理器')

    materials = db_manager.get_materials(project_id) or []
    audio_mats = [m for m in materials if m.get('type') == 'audio']
    video_mats = [m for m in materials if m.get('type') == 'video']

    if audio_mats:
        audio_path = _resolve_material_path(audio_mats[0].get('path'))
        if audio_path and audio_path.exists():
            return audio_path, False
        raise FileNotFoundError('音频素材文件不存在')

    if not video_mats:
        raise FileNotFoundError('项目中未找到可用的音频或视频素材')

    video_path = _resolve_material_path(video_mats[0].get('path'))
    if not video_path or not video_path.exists():
        raise FileNotFoundError('项目视频素材文件不存在')

    tmp_dir = BASE_DIR / 'temp'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_dir / f'{uuid.uuid4().hex}.wav'
    ffmpeg_path = _get_ffmpeg_executable()
    if not ffmpeg_path:
        raise RuntimeError('系统未检测到 FFmpeg，请安装后重试，或先添加音频素材')

    cmd = [
        ffmpeg_path, '-y', '-i', str(video_path),
        '-vn', '-ac', '1', '-ar', '16000',
        '-f', 'wav', str(audio_path)
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        logger.error('FFmpeg 提取音频超时（300s）')
        raise TimeoutError('提取音频超时（300s），请检查视频文件是否正常')
    if proc.returncode != 0:
        logger.error(f'FFmpeg 提取音频失败: {proc.stderr[:500]}')
        raise RuntimeError('提取音频失败：视频编码不被支持或文件不可读取')
    return audio_path, True


def _load_whisper_model(data, progress_callback=None):
    """加载 faster-whisper 模型，GPU 不可用时自动回退 CPU。"""
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise RuntimeError(f'缺少依赖 faster-whisper：{e}')

    model_size = (data.get('model_size') or 'tiny').strip()
    device_req = (data.get('device') or 'auto').lower()
    compute_type = (data.get('compute_type') or '').lower()
    if device_req == 'cpu':
        device = 'cpu'
        compute_type = compute_type or 'int8'
    elif device_req in ('cuda', 'gpu'):
        device = 'cuda'
        compute_type = compute_type or 'float16'
    else:
        device = 'cuda'
        compute_type = compute_type or 'float16'

    if progress_callback:
        progress_callback(f'正在加载 {model_size} 模型（{device}/{compute_type}），首次使用可能需要下载...')

    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        if progress_callback:
            progress_callback(f'{model_size} 模型加载完成')
        return model
    except Exception as first_error:
        logger.warning(f'无法以 {device}/{compute_type} 加载模型，退回 CPU: {first_error}')
        if progress_callback:
            progress_callback('GPU 加载失败，自动回退到 CPU 模式...')
        try:
            return WhisperModel(model_size, device='cpu', compute_type='int8')
        except Exception:
            raise RuntimeError(f'无法加载语音识别模型: {first_error}')


def _format_ass_time(seconds):
    """将秒数转换为 ASS 时间格式。"""
    total = max(0.0, float(seconds or 0.0))
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = int(total % 60)
    centis = int((total - int(total)) * 100)
    return f'{hours}:{minutes:02d}:{secs:02d}.{centis:02d}'


def _normalize_hex_color(value, default='#FFFFFF'):
    """标准化前端传入的十六进制颜色。"""
    text = str(value or default).strip()
    if text.startswith('#'):
        text = text[1:]
    if len(text) == 3:
        text = ''.join(ch + ch for ch in text)
    if len(text) != 6:
        text = str(default).lstrip('#')
    try:
        int(text, 16)
    except Exception:
        text = str(default).lstrip('#')
    return '#' + text.upper()


def _hex_to_ass_color(value, alpha='00'):
    """ASS 颜色使用 AABBGGRR 顺序。"""
    text = _normalize_hex_color(value).lstrip('#')
    red = text[0:2]
    green = text[2:4]
    blue = text[4:6]
    return f'&H{alpha}{blue}{green}{red}'


def _escape_ass_text(text):
    """转义 ASS 事件文本，避免样式控制符污染字幕内容。"""
    return (
        str(text or '')
        .replace('{', '(')
        .replace('}', ')')
        .replace('\r\n', '\n')
        .replace('\r', '\n')
        .replace('\n', r'\N')
        .strip()
    )


def _sanitize_subtitles(raw_subtitles):
    """清洗前端提交的字幕片段。"""
    if not isinstance(raw_subtitles, list):
        return []

    subtitles = []
    for item in raw_subtitles:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        if not text:
            continue
        try:
            start = max(0.0, float(item.get('start') or 0.0))
            end = max(start + 0.1, float(item.get('end') or 0.0))
        except Exception:
            continue
        subtitles.append({'start': start, 'end': end, 'text': text})
    return subtitles


def _resolve_video_path(data, db_manager):
    """从请求或项目素材中定位需要合成字幕的视频。"""
    video_path = data.get('video_path')
    if video_path:
        candidate = _resolve_material_path(video_path)
        if candidate and candidate.exists():
            return candidate

    project_id = data.get('project_id')
    if project_id and db_manager is not None:
        materials = db_manager.get_materials(project_id) or []
        for material in materials:
            if material.get('type') != 'video':
                continue
            candidate = _resolve_material_path(material.get('path'))
            if candidate and candidate.exists():
                return candidate

    return None


def _build_ass_content(subtitles, style):
    """根据统一样式生成 ASS 字幕内容。"""
    position = (style.get('position') or 'bottom').strip().lower()
    alignment_map = {'bottom': 2, 'center': 5, 'top': 8}
    alignment = alignment_map.get(position, 2)

    font_family = (
        style.get('font_family')
        or style.get('fontFamily')
        or style.get('font')
        or DEFAULT_FONT_NAME
    )
    font_family = str(font_family).strip() or DEFAULT_FONT_NAME

    try:
        font_size = int(float(style.get('font_size') or style.get('fontSize') or 48))
    except Exception:
        font_size = 48
    font_size = max(12, min(160, font_size))

    font_color = style.get('font_color') or style.get('fontColor') or '#FFFFFF'
    bg_color = style.get('bg_color') or style.get('bgColor') or '#000000'
    stroke_color = style.get('stroke_color') or style.get('strokeColor') or bg_color
    bold = -1 if bool(style.get('bold', True)) else 0

    primary = _hex_to_ass_color(font_color, '00')
    outline = _hex_to_ass_color(stroke_color, '00')
    back = _hex_to_ass_color(bg_color, '80')
    border_style = 3 if bg_color else 1

    lines = [
        '[Script Info]',
        'ScriptType: v4.00+',
        'PlayResX: 1920',
        'PlayResY: 1080',
        'ScaledBorderAndShadow: yes',
        '',
        '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        f'Style: Default,{font_family},{font_size},{primary},{primary},{outline},{back},{bold},0,0,0,100,100,0,0,{border_style},3,0,{alignment},80,80,70,1',
        '',
        '[Events]',
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text'
    ]

    for subtitle in subtitles:
        lines.append(
            'Dialogue: 0,'
            f'{_format_ass_time(subtitle["start"])},'
            f'{_format_ass_time(subtitle["end"])},'
            f'Default,,0,0,0,,{_escape_ass_text(subtitle["text"])}'
        )

    return '\n'.join(lines) + '\n'


def _escape_filter_path(path):
    """转义 FFmpeg subtitles 滤镜中的本地路径。"""
    text = str(path).replace('\\', '/')
    return text.replace(':', r'\:').replace("'", r"\'")


def _ffmpeg_has_filter(ffmpeg_path, filter_name):
    """检测当前 FFmpeg 是否支持指定滤镜。"""
    try:
        proc = subprocess.run(
            [ffmpeg_path, '-hide_banner', '-filters'],
            capture_output=True,
            text=True,
            timeout=8
        )
        return proc.returncode == 0 and filter_name in (proc.stdout or '')
    except Exception:
        return False


def _resolve_font_file(style):
    """从前端字体名解析到本地字体文件。"""
    font_value = (
        style.get('font_file')
        or style.get('fontFile')
        or style.get('font_family')
        or style.get('fontFamily')
        or style.get('font')
        or ''
    )
    text = str(font_value).strip()
    candidate = Path(text)
    if text and candidate.is_absolute() and candidate.exists():
        return candidate

    aliases = {
        'Microsoft YaHei': 'wryh.ttf',
        '微软雅黑': 'wryh.ttf',
        'PingFang SC': 'wryh.ttf',
        'Source Han Sans SC': '思源宋体-Bold.otf',
        '思源黑体': '思源宋体-Bold.otf',
        'SimHei': 'wryh.ttf',
        '黑体': 'wryh.ttf',
        'Arial': 'wryh.ttf',
    }
    names = []
    if text in aliases:
        names.append(aliases[text])
    if text:
        names.extend([text, f'{text}.ttf', f'{text}.otf'])
    names.append('wryh.ttf')

    for name in names:
        path = Path(FONTS_DIR) / name
        if path.exists():
            return path
    return None


def _wrap_text_for_width(draw, text, font, max_width):
    """按像素宽度给字幕断行，适配中文连续文本。"""
    paragraphs = str(text or '').splitlines() or ['']
    lines = []
    for paragraph in paragraphs:
        current = ''
        for ch in paragraph:
            trial = current + ch
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines[:3] or ['']


def _draw_subtitle_on_frame(frame, subtitle_text, style, font_file):
    """使用 Pillow 在单帧上绘制字幕。"""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.fromarray(frame[:, :, ::-1]).convert('RGBA')
    overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size

    try:
        font_size = int(float(style.get('font_size') or style.get('fontSize') or 48))
    except Exception:
        font_size = 48
    font_size = max(12, min(160, font_size))

    if font_file:
        font = ImageFont.truetype(str(font_file), font_size)
    else:
        font = ImageFont.load_default()

    max_text_width = int(width * 0.86)
    lines = _wrap_text_for_width(draw, subtitle_text, font, max_text_width)
    line_boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=2) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    text_width = max((box[2] - box[0] for box in line_boxes), default=0)
    line_gap = max(6, int(font_size * 0.18))
    text_height = sum(line_heights) + line_gap * max(0, len(lines) - 1)
    pad_x = max(14, int(font_size * 0.45))
    pad_y = max(8, int(font_size * 0.24))

    position = (style.get('position') or 'bottom').strip().lower()
    box_width = min(width - 24, text_width + pad_x * 2)
    box_height = text_height + pad_y * 2
    left = int((width - box_width) / 2)
    if position == 'top':
        top = int(height * 0.09)
    elif position == 'center':
        top = int((height - box_height) / 2)
    else:
        top = int(height - box_height - height * 0.09)
    top = max(8, min(height - box_height - 8, top))

    bg_hex = _normalize_hex_color(style.get('bg_color') or style.get('bgColor') or '#000000')
    bg_rgb = tuple(int(bg_hex[i:i + 2], 16) for i in (1, 3, 5))
    draw.rounded_rectangle(
        [left, top, left + box_width, top + box_height],
        radius=max(6, int(font_size * 0.16)),
        fill=(*bg_rgb, 178)
    )

    font_hex = _normalize_hex_color(style.get('font_color') or style.get('fontColor') or '#FFFFFF')
    font_rgb = tuple(int(font_hex[i:i + 2], 16) for i in (1, 3, 5))
    stroke_hex = _normalize_hex_color(style.get('stroke_color') or style.get('strokeColor') or '#000000')
    stroke_rgb = tuple(int(stroke_hex[i:i + 2], 16) for i in (1, 3, 5))

    y = top + pad_y
    for index, line in enumerate(lines):
        box = line_boxes[index]
        line_width = box[2] - box[0]
        x = int(left + (box_width - line_width) / 2)
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(*font_rgb, 255),
            stroke_width=2,
            stroke_fill=(*stroke_rgb, 255)
        )
        y += line_heights[index] + line_gap

    import numpy as np
    composed = Image.alpha_composite(image, overlay).convert('RGB')
    return np.array(composed)[:, :, ::-1]


def _render_video_with_pillow(video_path, output_path, subtitles, style, ffmpeg_path):
    """OpenCV + Pillow 后备渲染：逐帧绘制字幕，再合并原音频。"""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError('无法打开视频文件')

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError('无法读取视频尺寸')

    temp_video = output_path.with_suffix('.silent.mp4')
    writer = cv2.VideoWriter(
        str(temp_video),
        cv2.VideoWriter_fourcc(*'mp4v'),
        fps,
        (width, height)
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError('无法创建临时视频文件')

    font_file = _resolve_font_file(style)
    frame_index = 0
    subtitle_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            current_time = frame_index / fps
            while subtitle_index < len(subtitles) and current_time > subtitles[subtitle_index]['end']:
                subtitle_index += 1
            if (
                subtitle_index < len(subtitles)
                and subtitles[subtitle_index]['start'] <= current_time <= subtitles[subtitle_index]['end']
            ):
                frame = _draw_subtitle_on_frame(frame, subtitles[subtitle_index]['text'], style, font_file)
            writer.write(frame)
            frame_index += 1
    finally:
        cap.release()
        writer.release()

    cmd = [
        ffmpeg_path,
        '-y',
        '-i', str(temp_video),
        '-i', str(video_path),
        '-map', '0:v:0',
        '-map', '1:a?',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-crf', '20',
        '-c:a', 'copy',
        '-shortest',
        '-movflags', '+faststart',
        str(output_path)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    try:
        temp_video.unlink(missing_ok=True)
    except Exception:
        pass
    if proc.returncode != 0:
        logger.error(f'合并字幕视频音频失败: {proc.stderr[-1000:]}')
        raise RuntimeError('字幕视频渲染完成，但合并原音频失败')


def create_generate_subtitle_handler(db_manager):
    """创建自动字幕生成处理函数。"""
    def generate_subtitle():
        """基于项目音/视频素材生成自动字幕。"""
        try:
            data = request.get_json() or {}
            project_id = data.get('project_id')
            language = (data.get('language') or 'zh').split('-')[0]
            model_size = (data.get('model_size') or 'tiny').strip()

            if not project_id:
                return jsonify({'code': 1, 'msg': '缺少项目ID', 'data': None}), 400
            if db_manager is None:
                return jsonify({'code': 1, 'msg': '字幕生成服务未绑定数据库管理器', 'data': None}), 500

            materials = db_manager.get_materials(project_id) or []
            audio_mats = [m for m in materials if m.get('type') == 'audio']
            video_mats = [m for m in materials if m.get('type') == 'video']

            audio_path = None
            cleanup_tmp = False

            if audio_mats:
                audio_path = _resolve_material_path(audio_mats[0].get('path'))
            elif video_mats:
                video_path = _resolve_material_path(video_mats[0].get('path'))
                if not video_path or not video_path.exists():
                    return jsonify({'code': 1, 'msg': '项目视频素材文件不存在', 'data': None}), 400

                tmp_dir = BASE_DIR / 'temp'
                tmp_dir.mkdir(parents=True, exist_ok=True)
                audio_path = tmp_dir / f'{uuid.uuid4().hex}.wav'
                ffmpeg_path = _get_ffmpeg_executable()
                if not ffmpeg_path:
                    return jsonify({'code': 1, 'msg': '系统未检测到 FFmpeg，请安装后重试，或先添加音频素材', 'data': None}), 500

                cmd = [
                    ffmpeg_path, '-y', '-i', str(video_path),
                    '-vn', '-ac', '1', '-ar', '16000',
                    '-f', 'wav', str(audio_path)
                ]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                except FileNotFoundError:
                    return jsonify({'code': 1, 'msg': 'FFmpeg 可执行文件不可用，请检查安装路径或先添加音频素材', 'data': None}), 500
                except subprocess.TimeoutExpired:
                    return jsonify({'code': 1, 'msg': '提取音频超时（300s），请检查视频文件是否正常', 'data': None}), 500
                if proc.returncode != 0:
                    logger.error(f'FFmpeg 提取音频失败: {proc.stderr[:300]}')
                    return jsonify({'code': 1, 'msg': '提取音频失败：视频编码不被支持或文件不可读取', 'data': None}), 500
                cleanup_tmp = True
            else:
                return jsonify({'code': 1, 'msg': '项目中未找到可用的音频或视频素材', 'data': None}), 400

            if not audio_path or not Path(audio_path).exists():
                return jsonify({'code': 1, 'msg': '音频素材文件不存在', 'data': None}), 400

            try:
                from faster_whisper import WhisperModel
            except Exception as e:
                return jsonify({'code': 1, 'msg': f'缺少依赖 faster-whisper：{e}', 'data': None}), 500

            device_req = (data.get('device') or 'auto').lower()
            compute_type = (data.get('compute_type') or '').lower()
            if device_req == 'cpu':
                device = 'cpu'
                compute_type = compute_type or 'int8'
            elif device_req in ('cuda', 'gpu'):
                device = 'cuda'
                compute_type = compute_type or 'float16'
            else:
                device = 'cuda'
                compute_type = compute_type or 'float16'

            try:
                try:
                    model = WhisperModel(model_size, device=device, compute_type=compute_type)
                except Exception:
                    model = WhisperModel(model_size, device='cpu', compute_type='int8')

                segments, info = model.transcribe(
                    str(audio_path),
                    language=language,
                    beam_size=int(data.get('beam_size') or 5),
                    vad_filter=bool(data.get('vad_filter') if data.get('vad_filter') is not None else True)
                )
                subtitles = [_format_segment(seg) for seg in segments]
            finally:
                if cleanup_tmp:
                    try:
                        Path(audio_path).unlink(missing_ok=True)
                    except Exception:
                        pass

            if subtitles:
                _merge_subtitle_session(db_manager, project_id, {
                    'subtitles': subtitles,
                    'language': language
                })
                _update_project_status(db_manager, project_id, 'completed')

            return jsonify({
                'code': 0,
                'msg': '字幕生成成功',
                'data': {
                    'subtitles': subtitles,
                    'language': language
                }
            })
        except Exception as e:
            logger.error(f'字幕生成失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'字幕生成失败: {e}', 'data': None}), 500

    return generate_subtitle


def _run_generate_subtitle_task(task_id, data, db_manager):
    """后台执行字幕识别任务，持续写入进度和已识别片段。"""
    project_id = data.get('project_id')
    cleanup_tmp = False
    audio_path = None
    subtitles = []
    try:
        _update_project_status(db_manager, project_id, 'processing')
        _json_safe_task_update(db_manager, task_id, 'running', 3, {
            'message': '正在准备项目素材',
            'subtitles': subtitles
        })

        audio_path, cleanup_tmp = _extract_audio_from_project(data, db_manager)
        _json_safe_task_update(db_manager, task_id, 'running', 15, {
            'message': '音频准备完成，正在加载识别模型',
            'subtitles': subtitles
        })

        import time
        model = _load_whisper_model(data, progress_callback=lambda msg: (
            _json_safe_task_update(db_manager, task_id, 'running', 18, {
                'message': msg, 'subtitles': []
            })
        ))
        language = (data.get('language') or 'zh').split('-')[0]
        _json_safe_task_update(db_manager, task_id, 'running', 25, {
            'message': '模型加载完成，正在识别语音',
            'subtitles': subtitles,
            'language': language
        })

        segments_iter, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=int(data.get('beam_size') or 5),
            vad_filter=bool(data.get('vad_filter') if data.get('vad_filter') is not None else True)
        )
        duration = max(1.0, float(getattr(info, 'duration', 0.0) or 0.0))

        # 心跳看门狗：如果在 max(300, duration*2) 秒内没有新 segment，则判定为卡死
        _stall_timeout = max(300.0, duration * 2.0)
        _last_segment_time = time.time()

        for seg in segments_iter:
            _now = time.time()
            _elapsed = _now - _last_segment_time
            if _elapsed > _stall_timeout:
                raise TimeoutError(
                    f'语音识别卡死在 {_elapsed:.0f}s 位置'
                    f'（音频总长 {duration:.0f}s，超时阈值 {_stall_timeout:.0f}s）'
                )
            _last_segment_time = _now

            item = _format_segment(seg)
            if item.get('text'):
                subtitles.append(item)
            progress = min(95, 25 + int((float(item.get('end') or 0.0) / duration) * 70))
            _json_safe_task_update(db_manager, task_id, 'running', progress, {
                'message': f'已识别 {len(subtitles)} 条字幕',
                'subtitles': subtitles,
                'language': language
            })

        output_data = {
            'message': f'字幕生成完成，共 {len(subtitles)} 条',
            'subtitles': subtitles,
            'language': language
        }
        _json_safe_task_update(db_manager, task_id, 'completed', 100, output_data)
        _merge_subtitle_session(db_manager, project_id, {
            'subtitles': subtitles,
            'language': language,
            'last_generate_task_id': task_id
        })
        _update_project_status(db_manager, project_id, 'completed')
    except Exception as e:
        logger.error(f'字幕识别任务失败: {task_id}, {e}', exc_info=True)
        _json_safe_task_update(db_manager, task_id, 'failed', None, {
            'message': f'字幕生成失败: {e}',
            'subtitles': subtitles
        }, str(e))
        _update_project_status(db_manager, project_id, 'failed')
    finally:
        if cleanup_tmp and audio_path:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                pass


def create_generate_subtitle_task_handler(db_manager):
    """创建异步字幕识别任务处理函数。"""
    def generate_subtitle_task():
        try:
            data = request.get_json() or {}
            project_id = data.get('project_id')
            if not project_id:
                return jsonify({'code': 1, 'msg': '缺少项目ID', 'data': None}), 400
            if db_manager is None:
                return jsonify({'code': 1, 'msg': '字幕生成服务未绑定数据库管理器', 'data': None}), 500

            task_id = str(uuid.uuid4())
            input_data = dict(data)
            input_data['task_name'] = '自动字幕生成'
            db_manager.create_task(task_id, 'subtitle_generate', project_id, input_data=input_data)
            _update_project_status(db_manager, project_id, 'processing')
            threading.Thread(
                target=_run_generate_subtitle_task,
                args=(task_id, data, db_manager),
                daemon=False
            ).start()

            return jsonify({
                'code': 0,
                'msg': '字幕生成任务已创建',
                'data': {'task_id': task_id, 'project_id': project_id}
            })
        except Exception as e:
            logger.error(f'创建字幕生成任务失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'创建字幕生成任务失败: {e}', 'data': None}), 500

    return generate_subtitle_task


@subtitle_bp.route('/api/subtitle/<subtitle_id>', methods=['PUT'])
def update_subtitle(subtitle_id):
    """
    更新字幕内容和样式
    """
    try:
        data = request.json
        text = data.get('text')
        font_size = data.get('font_size', 24)
        font_color = data.get('font_color', '#FFFFFF')
        bg_color = data.get('bg_color', 'rgba(0,0,0,0.8)')
        font_bold = data.get('font_bold', False)
        font_italic = data.get('font_italic', False)
        font_underline = data.get('font_underline', False)
        
        logger.info(f"更新字幕: id={subtitle_id}, text={text}")
        
        if not text:
            return jsonify({
                'code': 1,
                'msg': '字幕内容不能为空'
            }), 400
        
        # 实际应用中会更新数据库
        # db_manager.update_subtitle(subtitle_id, {
        #     'text': text,
        #     'font_size': font_size,
        #     'font_color': font_color,
        #     'bg_color': bg_color,
        #     'font_bold': font_bold,
        #     'font_italic': font_italic,
        #     'font_underline': font_underline
        # })
        
        return jsonify({
            'code': 0,
            'msg': '字幕更新成功',
            'data': {
                'subtitle_id': subtitle_id,
                'text': text,
                'font_size': font_size,
                'font_color': font_color,
                'bg_color': bg_color,
                'font_bold': font_bold,
                'font_italic': font_italic,
                'font_underline': font_underline,
                'updated_at': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"更新字幕失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'字幕更新失败: {str(e)}'
        }), 500


@subtitle_bp.route('/api/subtitle/<subtitle_id>', methods=['DELETE'])
def delete_subtitle(subtitle_id):
    """
    删除字幕
    """
    try:
        logger.info(f"删除字幕: id={subtitle_id}")
        
        # 实际应用中会删除数据库记录
        # db_manager.delete_subtitle(subtitle_id)
        
        return jsonify({
            'code': 0,
            'msg': '字幕删除成功',
            'data': {
                'subtitle_id': subtitle_id
            }
        })
        
    except Exception as e:
        logger.error(f"删除字幕失败: {str(e)}")
        return jsonify({
            'code': 1,
            'msg': f'字幕删除失败: {str(e)}'
        }), 500


@subtitle_bp.route('/api/subtitle/export', methods=['POST'])
def export_subtitle():
    """旧版字幕导出入口（当前不再生成固定示例文件）

    实际的字幕导出建议在编辑器/项目导出流程中完成，
    由导出模块根据时间线与字幕脚本统一渲染并打包。

    为避免制造与真实项目不一致的 SRT 示例文件，此处仅返回
    明确的错误提示，引导调用方迁移到统一导出流程。
    """
    logger.warning('收到对旧版 /api/subtitle/export 的调用，当前不再生成示例 SRT 文件')
    return jsonify({
        'code': 1,
        'msg': '字幕导出请通过项目导出/编辑器流程完成，本旧版 /api/subtitle/export 不再生成示例SRT文件。',
        'data': None
    }), 410


@subtitle_bp.route('/api/subtitle/styles', methods=['GET'])
def get_subtitle_styles():
    """
    获取字幕样式预设
    """
    try:
        styles = []
        name_map = {
            'default': '默认样式',
            'large': '大号高亮',
            'small': '小号字幕',
            'colorful': '彩色强调',
            'zihun_wulongcha': '字魂·乌龙茶标题',
            'zihun_guochao': '字魂·国潮手书',
            'sourcehan_song_bold': '思源宋体（粗体）'
        }

        for style_id, cfg in SUBTITLE_STYLES.items():
            item = {
                'id': style_id,
                'name': name_map.get(style_id, style_id),
                'font': cfg.get('font'),
                'font_size': cfg.get('font_size'),
                'font_color': cfg.get('color'),
                'bg_color': cfg.get('bg_color'),
                'stroke_color': cfg.get('stroke_color'),
                'stroke_width': cfg.get('stroke_width'),
                'position': cfg.get('position', 'bottom')
            }
            styles.append(item)
    except Exception as e:
        logger.error(f"获取字幕样式预设失败: {e}")
        styles = []

    return jsonify({
        'code': 0,
        'msg': '获取成功',
        'data': {
            'styles': styles
        }
    })


def create_render_subtitle_video_handler(db_manager):
    """创建带字幕视频导出处理函数。"""
    def render_subtitle_video():
        """将字幕按统一样式烧录到视频并导出 MP4。"""
        try:
            data = request.get_json() or {}
            subtitles = _sanitize_subtitles(data.get('subtitles') or [])
            if not subtitles:
                return jsonify({'code': 1, 'msg': '请先生成或填写至少一条字幕', 'data': None}), 400

            video_path = _resolve_video_path(data, db_manager)
            if not video_path:
                return jsonify({'code': 1, 'msg': '未找到可用的视频文件', 'data': None}), 400

            ffmpeg_path = _get_ffmpeg_executable()
            if not ffmpeg_path:
                return jsonify({'code': 1, 'msg': '系统未检测到 FFmpeg，无法导出带字幕视频', 'data': None}), 500

            work_dir = BASE_DIR / 'temp' / 'subtitles'
            output_dir = BASE_DIR / 'output' / 'subtitles'
            work_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            export_id = uuid.uuid4().hex
            ass_path = work_dir / f'{export_id}.ass'
            output_path = output_dir / f'{export_id}.mp4'

            style = data.get('style') if isinstance(data.get('style'), dict) else {}
            ass_path.write_text(_build_ass_content(subtitles, style), encoding='utf-8')

            if _ffmpeg_has_filter(ffmpeg_path, 'subtitles'):
                subtitles_filter = f"subtitles=filename='{_escape_filter_path(ass_path)}'"
                if FONTS_DIR and Path(FONTS_DIR).exists():
                    subtitles_filter += f":fontsdir='{_escape_filter_path(FONTS_DIR)}'"

                cmd = [
                    ffmpeg_path,
                    '-y',
                    '-i', str(video_path),
                    '-vf', subtitles_filter,
                    '-c:v', 'libx264',
                    '-preset', 'veryfast',
                    '-crf', '20',
                    '-c:a', 'copy',
                    '-movflags', '+faststart',
                    str(output_path)
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if proc.returncode != 0:
                    logger.warning(f'FFmpeg subtitles 滤镜导出失败，改用逐帧渲染: {proc.stderr[-500:]}')
                    _render_video_with_pillow(video_path, output_path, subtitles, style, ffmpeg_path)
            else:
                logger.info('当前 FFmpeg 不支持 subtitles 滤镜，使用 OpenCV + Pillow 后备渲染')
                _render_video_with_pillow(video_path, output_path, subtitles, style, ffmpeg_path)

            return jsonify({
                'code': 0,
                'msg': '带字幕视频导出成功',
                'data': {
                    'output_path': f'output/subtitles/{output_path.name}',
                    'output_url': f'/output/subtitles/{output_path.name}',
                    'ass_path': f'temp/subtitles/{ass_path.name}'
                }
            })
        except Exception as e:
            logger.error(f'导出带字幕视频异常: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'导出带字幕视频失败: {e}', 'data': None}), 500

    return render_subtitle_video


def _run_render_subtitle_video_task(task_id, data, db_manager):
    """后台执行带字幕视频导出任务。"""
    project_id = data.get('project_id')
    try:
        _update_project_status(db_manager, project_id, 'processing')
        _json_safe_task_update(db_manager, task_id, 'running', 5, {'message': '正在校验字幕和视频'})

        subtitles = _sanitize_subtitles(data.get('subtitles') or [])
        if not subtitles:
            raise ValueError('请先生成或填写至少一条字幕')

        video_path = _resolve_video_path(data, db_manager)
        if not video_path:
            raise FileNotFoundError('未找到可用的视频文件')

        ffmpeg_path = _get_ffmpeg_executable()
        if not ffmpeg_path:
            raise RuntimeError('系统未检测到 FFmpeg，无法导出带字幕视频')

        work_dir = BASE_DIR / 'temp' / 'subtitles'
        output_dir = BASE_DIR / 'output' / 'subtitles'
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        export_id = uuid.uuid4().hex
        ass_path = work_dir / f'{export_id}.ass'
        output_path = output_dir / f'{export_id}.mp4'
        style = data.get('style') if isinstance(data.get('style'), dict) else {}
        ass_path.write_text(_build_ass_content(subtitles, style), encoding='utf-8')

        _json_safe_task_update(db_manager, task_id, 'running', 20, {
            'message': '字幕样式文件已生成，正在渲染视频',
            'subtitle_count': len(subtitles)
        })

        if _ffmpeg_has_filter(ffmpeg_path, 'subtitles'):
            subtitles_filter = f"subtitles=filename='{_escape_filter_path(ass_path)}'"
            if FONTS_DIR and Path(FONTS_DIR).exists():
                subtitles_filter += f":fontsdir='{_escape_filter_path(FONTS_DIR)}'"
            cmd = [
                ffmpeg_path, '-y', '-i', str(video_path),
                '-vf', subtitles_filter,
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                '-c:a', 'copy', '-movflags', '+faststart',
                str(output_path)
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0:
                logger.warning(f'FFmpeg subtitles 滤镜导出失败，改用逐帧渲染: {proc.stderr[-500:]}')
                _render_video_with_pillow(video_path, output_path, subtitles, style, ffmpeg_path)
        else:
            _render_video_with_pillow(video_path, output_path, subtitles, style, ffmpeg_path)

        output_data = {
            'message': '带字幕视频导出完成',
            'output_path': f'output/subtitles/{output_path.name}',
            'output_url': f'/output/subtitles/{output_path.name}',
            'ass_path': f'temp/subtitles/{ass_path.name}',
            'subtitle_count': len(subtitles)
        }
        _json_safe_task_update(db_manager, task_id, 'completed', 100, output_data)
        _merge_subtitle_session(db_manager, project_id, {
            'subtitles': subtitles,
            'style': _normalize_subtitle_style(style),
            'rendered_video_url': output_data['output_url'],
            'rendered_video_path': output_data['output_path'],
            'last_render_task_id': task_id
        })
        _update_project_status(db_manager, project_id, 'completed')
    except Exception as e:
        logger.error(f'带字幕视频导出任务失败: {task_id}, {e}', exc_info=True)
        _json_safe_task_update(db_manager, task_id, 'failed', None, {
            'message': f'导出带字幕视频失败: {e}'
        }, str(e))
        _update_project_status(db_manager, project_id, 'failed')


def create_render_subtitle_video_task_handler(db_manager):
    """创建异步带字幕视频导出处理函数。"""
    def render_subtitle_video_task():
        try:
            data = request.get_json() or {}
            project_id = data.get('project_id')
            if not project_id:
                return jsonify({'code': 1, 'msg': '缺少项目ID', 'data': None}), 400
            if db_manager is None:
                return jsonify({'code': 1, 'msg': '字幕导出服务未绑定数据库管理器', 'data': None}), 500

            task_id = str(uuid.uuid4())
            input_data = {
                'project_id': project_id,
                'video_path': data.get('video_path'),
                'style': data.get('style') or {},
                'subtitle_count': len(data.get('subtitles') or []),
                'task_name': '导出带字幕视频'
            }
            db_manager.create_task(task_id, 'subtitle_render_video', project_id, input_data=input_data)
            _update_project_status(db_manager, project_id, 'processing')
            threading.Thread(
                target=_run_render_subtitle_video_task,
                args=(task_id, data, db_manager),
                daemon=False
            ).start()

            return jsonify({
                'code': 0,
                'msg': '带字幕视频导出任务已创建',
                'data': {'task_id': task_id, 'project_id': project_id}
            })
        except Exception as e:
            logger.error(f'创建带字幕视频导出任务失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'创建导出任务失败: {e}', 'data': None}), 500

    return render_subtitle_video_task


def _build_session_payload(db_manager, project_id):
    """组装字幕工具页面可恢复的完整工作区数据。"""
    project = db_manager.get_project(project_id)
    if not project:
        return None

    materials = project.get('materials') or db_manager.get_materials(project_id) or []
    tasks = project.get('tasks') or db_manager.get_tasks(project_id) or []
    video = _find_video_material(materials)
    saved = _get_saved_subtitle_session(project)

    completed_gen = _latest_task(tasks, 'subtitle_generate', ['completed'])
    completed_render = _latest_task(tasks, 'subtitle_render_video', ['completed'])
    active_task = _latest_task(tasks, statuses=['pending', 'running'])
    if active_task and not _is_recent_active_task(active_task):
        logger.info(f'忽略过期字幕任务恢复轮询: {active_task.get("id")}')
        active_task = None

    subtitles = _normalize_subtitle_items(saved.get('subtitles'))
    if not subtitles:
        subtitles = _latest_completed_subtitles(db_manager, project_id, project)

    rendered_video_url = saved.get('rendered_video_url') or ''
    if not rendered_video_url and completed_render:
        rendered_video_url = _task_output(completed_render).get('output_url') or ''

    style = _normalize_subtitle_style(saved.get('style') or {})

    return {
        'project_id': project_id,
        'project': {
            'id': project_id,
            'name': project.get('name') or '自动字幕项目',
            'status': project.get('status') or 'draft',
            'created_at': project.get('created_at'),
            'updated_at': project.get('updated_at')
        },
        'server_video_path': saved.get('server_video_path') or (video or {}).get('path') or '',
        'video_name': (video or {}).get('name') or saved.get('video_name') or '',
        'subtitles': subtitles,
        'style': style,
        'rendered_video_url': rendered_video_url,
        'current_task_id': (active_task or {}).get('id') or '',
        'current_task_type': (active_task or {}).get('type') or '',
        'current_task_status': (active_task or {}).get('status') or '',
        'current_task_progress': (active_task or {}).get('progress') or 0,
        'tasks': tasks,
        'task_count': len(tasks),
        'subtitle_count': len(subtitles)
    }


def create_session_handler(db_manager):
    """创建字幕工具会话恢复处理函数。"""
    def get_session(project_id):
        """根据项目ID从数据库恢复字幕工具会话数据。"""
        if not db_manager:
            return jsonify({'code': 1, 'msg': '数据库服务未就绪', 'data': None}), 500

        try:
            payload = _build_session_payload(db_manager, project_id)
            if not payload:
                return jsonify({'code': 1, 'msg': '项目不存在', 'data': None}), 404
            return jsonify({'code': 0, 'msg': '会话数据恢复成功', 'data': payload})
        except Exception as e:
            logger.error(f'恢复字幕会话失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'恢复会话失败: {e}', 'data': None}), 500

    return get_session


def create_session_save_handler(db_manager):
    """创建字幕工具会话保存处理函数。"""
    def save_session(project_id):
        if not db_manager:
            return jsonify({'code': 1, 'msg': '数据库服务未就绪', 'data': None}), 500
        try:
            data = request.get_json() or {}
            updates = {}
            if 'server_video_path' in data:
                updates['server_video_path'] = data.get('server_video_path') or ''
            if 'video_name' in data:
                updates['video_name'] = data.get('video_name') or ''
            if 'subtitles' in data:
                incoming_subtitles = _normalize_subtitle_items(data.get('subtitles') or [])
                if incoming_subtitles:
                    updates['subtitles'] = incoming_subtitles
                else:
                    project = db_manager.get_project(project_id)
                    saved = _get_saved_subtitle_session(project)
                    existing_subtitles = _normalize_subtitle_items(saved.get('subtitles'))
                    fallback_subtitles = _latest_completed_subtitles(db_manager, project_id, project)
                    if not existing_subtitles and not fallback_subtitles:
                        updates['subtitles'] = []
            if 'style' in data:
                updates['style'] = _normalize_subtitle_style(data.get('style') or {})
            if 'rendered_video_url' in data:
                updates['rendered_video_url'] = data.get('rendered_video_url') or ''
            if 'language' in data:
                updates['language'] = data.get('language') or ''
            _merge_subtitle_session(db_manager, project_id, updates)
            payload = _build_session_payload(db_manager, project_id)
            return jsonify({'code': 0, 'msg': '字幕工作区已保存', 'data': payload})
        except Exception as e:
            logger.error(f'保存字幕会话失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'保存会话失败: {e}', 'data': None}), 500

    return save_session


def create_session_list_handler(db_manager):
    """创建字幕项目历史列表处理函数。"""
    def list_sessions():
        if not db_manager:
            return jsonify({'code': 1, 'msg': '数据库服务未就绪', 'data': None}), 500
        try:
            limit = request.args.get('limit', default=30, type=int)
            limit = max(1, min(limit or 30, 100))
            projects = db_manager.get_all_projects('subtitle') or []
            projects.sort(key=lambda item: item.get('updated_at') or item.get('created_at') or '', reverse=True)

            sessions = []
            for project in projects[:limit]:
                payload = _build_session_payload(db_manager, project.get('id'))
                if not payload:
                    continue
                active_label = ''
                if payload.get('current_task_id'):
                    active_label = payload.get('current_task_type') or '任务'
                sessions.append({
                    'project_id': payload['project_id'],
                    'name': payload['project']['name'],
                    'status': payload['project']['status'],
                    'created_at': payload['project']['created_at'],
                    'updated_at': payload['project']['updated_at'],
                    'video_name': payload.get('video_name') or '未命名视频',
                    'server_video_path': payload.get('server_video_path') or '',
                    'subtitle_count': payload.get('subtitle_count') or 0,
                    'task_count': payload.get('task_count') or 0,
                    'rendered_video_url': payload.get('rendered_video_url') or '',
                    'current_task_id': payload.get('current_task_id') or '',
                    'current_task_type': payload.get('current_task_type') or '',
                    'current_task_progress': payload.get('current_task_progress') or 0,
                    'active_label': active_label
                })

            return jsonify({
                'code': 0,
                'msg': '获取字幕项目记录成功',
                'data': {'sessions': sessions, 'total': len(sessions)}
            })
        except Exception as e:
            logger.error(f'获取字幕项目记录失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'获取字幕项目记录失败: {e}', 'data': None}), 500

    return list_sessions


def register_subtitle_routes(app, db_manager=None):
    """
    注册字幕API路由
    """
    app.add_url_rule(
        '/api/subtitle/sessions',
        'subtitle_sessions',
        create_session_list_handler(db_manager),
        methods=['GET']
    )
    app.add_url_rule(
        '/api/subtitle/session/<project_id>',
        'subtitle_session',
        create_session_handler(db_manager),
        methods=['GET']
    )
    app.add_url_rule(
        '/api/subtitle/session/<project_id>',
        'subtitle_session_save',
        create_session_save_handler(db_manager),
        methods=['POST']
    )
    app.add_url_rule(
        '/api/subtitle/generate',
        'subtitle_generate',
        create_generate_subtitle_handler(db_manager),
        methods=['POST']
    )
    app.add_url_rule(
        '/api/subtitle/generate-task',
        'subtitle_generate_task',
        create_generate_subtitle_task_handler(db_manager),
        methods=['POST']
    )
    app.add_url_rule(
        '/api/subtitle/render-video',
        'subtitle_render_video',
        create_render_subtitle_video_handler(db_manager),
        methods=['POST']
    )
    app.add_url_rule(
        '/api/subtitle/render-video-task',
        'subtitle_render_video_task',
        create_render_subtitle_video_task_handler(db_manager),
        methods=['POST']
    )
    app.register_blueprint(subtitle_bp)
    logger.info("字幕API路由注册成功")
