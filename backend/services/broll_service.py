# -*- coding: utf-8 -*-
"""字幕驱动自动补画面业务服务。"""

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from backend.config.paths import PROJECT_ROOT
from backend.engine.broll_composer import BrollComposer
from backend.services.stock_video import (
    InternetArchiveProvider,
    NasaVideoProvider,
    PexelsProvider,
    PixabayProvider,
    WikimediaCommonsProvider,
    VidevoProvider,
    VideezyProvider,
    MazwaiProvider,
    LifeOfVidsProvider,
    SplitshireProvider,
    CoverrProvider
)
from backend.services.stock_video.base_provider import ProviderError
from backend.utils.license_manifest import write_license_manifest

logger = logging.getLogger(__name__)


class BrollService:
    """补画面业务编排服务。"""

    DEFAULT_CONFIG = {
        'providers': ['wikimedia', 'internet_archive', 'nasa', 'videvo', 'videezy', 'mazwai', 'lifeofvids', 'splitshire', 'coverr', 'pexels', 'pixabay'],
        'default_quality': 'hd',
        'max_candidates_per_shot': 3,
        'max_download_mb_per_project': 2048,
        'cache_days': 14,
        'request_timeout_seconds': 12,
        'prefer_orientation': 'landscape'
    }

    STOP_WORDS = {
        '这个', '那个', '我们', '你们', '他们', '它们', '一个', '一种', '因为', '所以', '如果', '但是',
        '然后', '就是', '可以', '没有', '不是', '正在', '开始', '时候', '通过', '这些', '那些'
    }

    SAFE_CONTENT_BLACKLIST = {
        '血', '血腥', '暴力', '尸体', '尸首', '枪击', '枪杀', '枪战', '砍杀', '斩首', '虐杀', '屠杀',
        '爆炸', '炸弹', '火并', '火灾', '车祸', '伤亡', '死亡', '死者', '战场', '恐怖袭击', '武器',
        'gore', 'bloody', 'blood', 'violence', 'kill', 'murder', 'dead', 'death', 'weapon', 'gun'
    }

    NEWS_TOPIC_HINTS = {
        '政治': ['news footage', 'press conference', 'government meeting'],
        '时政': ['news footage', 'press conference', 'government meeting'],
        '外交': ['press conference', 'diplomatic meeting', 'news footage'],
        '军事': ['news footage military', 'defense briefing', 'military parade'],
        '国防': ['news footage military', 'defense briefing', 'military parade'],
        '军队': ['news footage military', 'defense briefing', 'military parade'],
        '会议': ['press conference', 'government meeting', 'news footage'],
        '新闻': ['news footage', 'press conference', 'reporter'],
        '发布会': ['press conference', 'news footage', 'reporter']
    }

    KEYWORD_TRANSLATIONS = {
        '城市': 'city skyline',
        '街道': 'street',
        '交通': 'traffic',
        '人流': 'crowd walking',
        '商业': 'business',
        '商务': 'business meeting',
        '办公': 'office work',
        '科技': 'technology',
        '地球': 'earth',
        '太空': 'space',
        '宇宙': 'space',
        '未来': 'future technology',
        '星球': 'planet',
        '电脑': 'computer',
        '手机': 'smartphone',
        '网络': 'internet technology',
        '数据': 'data analytics',
        '教育': 'education classroom',
        '学校': 'school',
        '学习': 'studying',
        '医疗': 'medical healthcare',
        '健康': 'healthy lifestyle',
        '运动': 'sports fitness',
        '美食': 'food cooking',
        '餐厅': 'restaurant',
        '旅行': 'travel',
        '风景': 'landscape',
        '自然': 'nature',
        '森林': 'forest',
        '山': 'mountain',
        '海': 'ocean',
        '河': 'river',
        '阳光': 'sunlight',
        '夜晚': 'night city',
        '家庭': 'family',
        '孩子': 'children',
        '汽车': 'car',
        '工厂': 'factory',
        '农业': 'agriculture',
        '会议': 'meeting',
        '金融': 'finance',
        '建筑': 'architecture',
        '公园': 'park',
        '乡村': 'countryside',
        '音乐': 'music',
        '舞台': 'stage performance'
    }

    def __init__(self, db_manager, socketio=None):
        self.db_manager = db_manager
        self.socketio = socketio
        self.cache_dir = PROJECT_ROOT / 'uploads' / 'stock_videos'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_session(self, project_id: str) -> Dict:
        project = self.db_manager.get_project(project_id)
        if not project:
            raise ValueError('项目不存在')
        result = self._project_result(project)
        session = result.get('broll_session')
        if not isinstance(session, dict):
            session = self._empty_session(project)
        return session

    def save_session(self, project_id: str, updates: Dict) -> Dict:
        project = self.db_manager.get_project(project_id)
        if not project:
            raise ValueError('项目不存在')
        result = self._project_result(project)
        session = result.get('broll_session')
        if not isinstance(session, dict):
            session = self._empty_session(project)
        session.update(updates or {})
        session['updated_at'] = datetime.now().isoformat(timespec='seconds')
        result['broll_session'] = session
        self.db_manager.update_project(project_id, {'result': result})
        return session

    def get_provider_status(self) -> Dict:
        providers = self._build_providers()
        statuses = [provider.status() for provider in providers.values()]
        return {
            'providers': statuses,
            'available': [item['provider'] for item in statuses if item.get('available')],
            'missing': [item['provider'] for item in statuses if not item.get('available')]
        }

    def create_plan_task(self, data: Dict) -> str:
        return self._create_and_start_task('broll_plan', data.get('project_id'), data, self._run_plan_task)

    def create_search_task(self, data: Dict) -> str:
        return self._create_and_start_task('broll_search', data.get('project_id'), data, self._run_search_task)

    def create_download_task(self, data: Dict) -> str:
        return self._create_and_start_task('broll_download', data.get('project_id'), data, self._run_download_task)

    def create_compose_task(self, data: Dict) -> str:
        return self._create_and_start_task('broll_compose', data.get('project_id'), data, self._run_compose_task)

    def export_license_manifest(self, project_id: str) -> Dict:
        session = self.get_session(project_id)
        manifest = write_license_manifest(project_id, session)
        session['license_manifest_url'] = manifest['url']
        self.save_session(project_id, session)
        return manifest

    def _create_and_start_task(self, task_type: str, project_id: str, data: Dict, target) -> str:
        if not project_id:
            raise ValueError('缺少项目ID')
        task_id = str(uuid.uuid4())
        input_data = dict(data or {})
        input_data['task_name'] = self._task_name(task_type)
        self.db_manager.create_task(task_id, task_type, project_id, input_data=input_data)
        self._update_project_status(project_id, 'processing')
        threading.Thread(target=target, args=(task_id, input_data), daemon=False).start()
        return task_id

    def _run_plan_task(self, task_id: str, data: Dict):
        project_id = data.get('project_id')
        try:
            self._task_update(task_id, 'running', 5, {'message': '正在读取字幕项目'})
            project = self.db_manager.get_project(project_id)
            if not project:
                raise ValueError('项目不存在')
            subtitles = self._get_subtitles(project, data)
            if not subtitles:
                raise ValueError('请先生成字幕，再生成补画面方案')

            self._task_update(task_id, 'running', 35, {'message': '正在生成镜头计划'})
            session = self._empty_session(project)
            session.update({
                'aspect_ratio': data.get('aspect_ratio') or 'original',
                'subtitle_mode': data.get('subtitle_mode') or 'burned',
                'providers': data.get('providers') or list(self.DEFAULT_CONFIG['providers']),
                # 保存分段配置
                'min_shot_duration': float(data.get('min_shot_duration', 3.0)),
                'max_shot_duration': float(data.get('max_shot_duration', 8.0)),
                'prefer_sentence_boundary': self._as_bool(data.get('prefer_sentence_boundary'), True),
                'shots': self._build_shots(subtitles, data)
            })
            saved = self.save_session(project_id, session)
            output = {
                'message': f'补画面方案已生成，共 {len(saved.get("shots") or [])} 个镜头',
                'broll_session': saved,
                'shots': saved.get('shots') or []
            }
            self._task_update(task_id, 'completed', 100, output)
            self._update_project_status(project_id, 'completed')
        except Exception as e:
            logger.error(f'补画面方案任务失败: {task_id}, {e}', exc_info=True)
            self._task_update(task_id, 'failed', None, {'message': f'生成补画面方案失败: {e}'}, str(e))
            self._update_project_status(project_id, 'failed')

    def _run_search_task(self, task_id: str, data: Dict):
        project_id = data.get('project_id')
        try:
            session = self.get_session(project_id)
            shots = session.get('shots') or []
            if not shots:
                raise ValueError('请先生成补画面方案')
            target_ids = self._resolve_search_targets(data, shots)
            if target_ids:
                shots = [shot for shot in shots if shot.get('shot_id') in target_ids]
                if not shots:
                    raise ValueError('未找到需要替换的镜头')

            providers = self._build_providers()
            enabled_names = data.get('providers') or session.get('providers') or list(self.DEFAULT_CONFIG['providers'])
            enabled = [providers[name] for name in enabled_names if name in providers and providers[name].available]
            if not enabled:
                raise ValueError('没有可用素材源。免 Key 素材源不可用，或已被配置关闭；请检查网络后重试')

            max_candidates = max(1, min(3, int(self._stock_config().get('max_candidates_per_shot') or 3)))
            orientation = self._stock_config().get('prefer_orientation') or 'landscape'

            for index, shot in enumerate(shots, start=1):
                if not target_ids and shot.get('locked') and shot.get('candidates'):
                    continue
                progress = 5 + int(index / max(1, len(shots)) * 85)
                self._task_update(task_id, 'running', progress, {
                    'message': f'正在搜索镜头素材 {index}/{len(shots)}',
                    'shots': shots
                })
                candidates = self._search_candidates_for_shot(shot, enabled, orientation, max_candidates)
                shot['candidates'] = candidates
                if candidates and (not shot.get('selected_candidate_id') or target_ids):
                    shot['selected_candidate_id'] = candidates[0]['candidate_id']
                elif not candidates:
                    shot['selected_candidate_id'] = ''

            if target_ids:
                all_shots = session.get('shots') or []
                target_map = {shot.get('shot_id'): shot for shot in shots}
                session['shots'] = [target_map.get(shot.get('shot_id'), shot) for shot in all_shots]
            else:
                session['shots'] = shots
            session['updated_at'] = datetime.now().isoformat(timespec='seconds')
            saved = self.save_session(project_id, session)
            if not target_ids:
                message = '素材候选搜索完成'
            elif len(target_ids) == 1:
                message = '当前镜头素材已更新'
            else:
                message = '选中镜头素材已更新'
            output = {
                'message': message,
                'broll_session': saved,
                'shots': saved.get('shots') or []
            }
            self._task_update(task_id, 'completed', 100, output)
            self._update_project_status(project_id, 'completed')
        except Exception as e:
            logger.error(f'补画面素材搜索任务失败: {task_id}, {e}', exc_info=True)
            self._task_update(task_id, 'failed', None, {'message': f'搜索素材失败: {e}'}, str(e))
            self._update_project_status(project_id, 'failed')

    def _run_download_task(self, task_id: str, data: Dict):
        project_id = data.get('project_id')
        try:
            session = self.get_session(project_id)
            shots = session.get('shots') or []
            if not shots:
                raise ValueError('请先搜索素材候选')

            selected_count = 0
            for index, shot in enumerate(shots, start=1):
                progress = 5 + int(index / max(1, len(shots)) * 85)
                self._task_update(task_id, 'running', progress, {
                    'message': f'正在下载素材 {index}/{len(shots)}',
                    'shots': shots
                })
                if shot.get('skipped'):
                    continue
                candidate = self._selected_candidate(shot)
                if not candidate:
                    continue
                local_path = self._download_candidate(candidate)
                candidate['local_path'] = local_path
                shot['selected_candidate_id'] = candidate.get('candidate_id') or shot.get('selected_candidate_id') or ''
                self._register_material(project_id, shot, candidate, local_path)
                selected_count += 1

            session['shots'] = shots
            saved = self.save_session(project_id, session)
            output = {
                'message': f'素材下载完成，共下载 {selected_count} 个素材',
                'broll_session': saved,
                'shots': saved.get('shots') or []
            }
            self._task_update(task_id, 'completed', 100, output)
            self._update_project_status(project_id, 'completed')
        except Exception as e:
            logger.error(f'补画面素材下载任务失败: {task_id}, {e}', exc_info=True)
            self._task_update(task_id, 'failed', None, {'message': f'下载素材失败: {e}'}, str(e))
            self._update_project_status(project_id, 'failed')

    def _run_compose_task(self, task_id: str, data: Dict):
        project_id = data.get('project_id')
        try:
            session = self.get_session(project_id)
            project = self.db_manager.get_project(project_id)
            if not project:
                raise ValueError('项目不存在')
            source_video_path = data.get('source_video_path') or session.get('source_video_path')
            if not source_video_path:
                raise ValueError('未找到原视频路径')

            if data.get('aspect_ratio'):
                session['aspect_ratio'] = data.get('aspect_ratio')
            if data.get('subtitle_mode'):
                session['subtitle_mode'] = data.get('subtitle_mode')
            subtitles = self._get_subtitles(project, data)
            style = self._get_subtitle_style(project, data)
            shots = session.get('shots') or []
            if not shots:
                raise ValueError('请先生成补画面方案并搜索素材')

            composer = BrollComposer()

            def progress(value, message):
                mapped_value = 25 + int(max(0, min(100, value)) * 0.7)
                self._task_update(task_id, 'running', mapped_value, {
                    'message': message,
                    'broll_session': session
                })

            self._task_update(task_id, 'running', 5, {'message': '正在准备补画面合成'})
            asset_result = self._ensure_compose_assets(project_id, shots, task_id)
            if asset_result.get('usable', 0) <= 0:
                raise ValueError('没有可用于合成的补画面素材，请先搜索素材并确认候选素材可下载')
            session['shots'] = shots
            session['updated_at'] = datetime.now().isoformat(timespec='seconds')
            self.save_session(project_id, session)

            result = composer.compose(
                project_id=project_id,
                source_video_path=source_video_path,
                shots=shots,
                subtitles=subtitles,
                style=style,
                config={
                    'aspect_ratio': session.get('aspect_ratio') or 'original',
                    'subtitle_mode': session.get('subtitle_mode') or 'burned'
                },
                progress_callback=progress
            )
            session['rendered_video_url'] = result.get('output_url') or ''
            manifest = write_license_manifest(project_id, session)
            session['license_manifest_url'] = manifest.get('url') or ''
            saved = self.save_session(project_id, session)
            message = '补画面视频合成完成'
            if asset_result.get('downloaded', 0) > 0:
                message = f"补画面视频合成完成，已自动下载 {asset_result.get('downloaded')} 个素材"
            if asset_result.get('failed', 0) > 0:
                message = f"{message}；{asset_result.get('failed')} 个镜头素材下载失败，已使用原视频兜底"
            output = {
                'message': message,
                'output_url': result.get('output_url') or '',
                'output_path': result.get('output_path') or '',
                'asset_result': asset_result,
                'license_manifest_url': manifest.get('url') or '',
                'broll_session': saved
            }
            self._task_update(task_id, 'completed', 100, output)
            self._update_project_status(project_id, 'completed')
        except Exception as e:
            logger.error(f'补画面合成任务失败: {task_id}, {e}', exc_info=True)
            self._task_update(task_id, 'failed', None, {'message': f'合成补画面视频失败: {e}'}, str(e))
            self._update_project_status(project_id, 'failed')

    def _empty_session(self, project: Dict) -> Dict:
        subtitle_session = self._subtitle_session(project)
        video = self._find_video_material(project.get('materials') or [])
        return {
            'version': 1,
            'source_project_id': project.get('id') or '',
            'source_video_path': subtitle_session.get('server_video_path') or (video or {}).get('path') or '',
            'audio_mode': 'keep_original',
            'subtitle_mode': 'burned',
            'aspect_ratio': 'original',
            'providers': list(self.DEFAULT_CONFIG['providers']),
            'shots': [],
            'rendered_video_url': '',
            'license_manifest_url': '',
            'updated_at': datetime.now().isoformat(timespec='seconds')
        }

    def _build_shots(self, subtitles: List[Dict], data: Dict) -> List[Dict]:
        merged = self._nlp_segment_subtitles(subtitles, data)
        shots = []
        for index, item in enumerate(merged, start=1):
            keywords = self._extract_keywords(item.get('text') or '', data.get('topic') or '')
            search_queries = self._build_search_queries(keywords, item.get('text') or '', data.get('topic') or '')
            start = round(float(item.get('start') or 0.0), 3)
            end = round(float(item.get('end') or start + 0.1), 3)
            shots.append({
                'shot_id': f's{index:03d}',
                'start': start,
                'end': end,
                'duration': round(max(0.1, end - start), 3),
                'subtitle_text': item.get('text') or '',
                'subtitle_indices': item.get('subtitle_indices') or [],
                'theme': item.get('theme') or '、'.join(keywords[:4]),
                'keywords': keywords,
                'search_queries': search_queries,
                'locked': False,
                'skipped': False,
                'selected_candidate_id': '',
                'candidates': []
            })
        return shots

    def _nlp_segment_subtitles(self, subtitles: List[Dict], data: Dict) -> List[Dict]:
        """按完整语义把一条或多条字幕合并为补画面镜头。"""
        normalized = self._normalize_subtitles(subtitles)
        if not normalized:
            return []

        min_duration, max_duration, prefer_sentence = self._segment_config(data)
        segments = []
        current = None

        for index, subtitle in enumerate(normalized):
            if current is None:
                current = self._new_segment(subtitle, index)
            else:
                self._append_subtitle_to_segment(current, subtitle, index)

            next_subtitle = normalized[index + 1] if index + 1 < len(normalized) else None
            if next_subtitle and self._should_close_segment(
                current,
                subtitle,
                next_subtitle,
                min_duration,
                max_duration,
                prefer_sentence
            ):
                self._finalize_segment(current)
                segments.append(current)
                current = None

        if current:
            self._finalize_segment(current)
            segments.append(current)

        return self._rebalance_short_segments(segments, min_duration, max_duration)

    def _segment_config(self, data: Dict):
        try:
            min_duration = float((data or {}).get('min_shot_duration', 3.0))
        except Exception:
            min_duration = 3.0
        try:
            max_duration = float((data or {}).get('max_shot_duration', 8.0))
        except Exception:
            max_duration = 8.0

        min_duration = max(0.5, min_duration)
        max_duration = max(min_duration + 0.5, max_duration)
        prefer_sentence = self._as_bool((data or {}).get('prefer_sentence_boundary'), True)
        return min_duration, max_duration, prefer_sentence

    @staticmethod
    def _as_bool(value, default=False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'yes', 'on', '是', '开启'}
        return bool(value)

    def _new_segment(self, subtitle: Dict, index: int) -> Dict:
        text = str(subtitle.get('text') or '').strip()
        return {
            'start': float(subtitle.get('start') or 0.0),
            'end': float(subtitle.get('end') or 0.0),
            'text': text,
            'keywords': self._segment_keywords(text),
            'subtitle_indices': [index]
        }

    def _append_subtitle_to_segment(self, segment: Dict, subtitle: Dict, index: int):
        text = str(subtitle.get('text') or '').strip()
        segment['end'] = float(subtitle.get('end') or segment.get('end') or 0.0)
        segment['text'] = f"{segment.get('text') or ''} {text}".strip()
        segment['keywords'] = self._merge_unique(segment.get('keywords') or [], self._segment_keywords(text), limit=10)
        segment.setdefault('subtitle_indices', []).append(index)

    def _should_close_segment(
        self,
        segment: Dict,
        subtitle: Dict,
        next_subtitle: Dict,
        min_duration: float,
        max_duration: float,
        prefer_sentence: bool
    ) -> bool:
        duration = float(segment.get('end') or 0.0) - float(segment.get('start') or 0.0)
        text = str(subtitle.get('text') or '').strip()
        next_text = str(next_subtitle.get('text') or '').strip()
        gap = float(next_subtitle.get('start') or 0.0) - float(segment.get('end') or 0.0)
        sentence_end = self._is_sentence_boundary(text)
        incomplete = self._ends_with_incomplete_phrase(segment.get('text') or '')
        continuation = self._starts_with_continuation(next_text)
        topic_change = self._is_topic_change(segment.get('keywords') or [], self._segment_keywords(next_text))

        if duration >= max_duration:
            return not incomplete or duration >= max_duration + 2.0
        if duration < min_duration:
            return False
        if gap >= 1.5 and not incomplete:
            return True

        if prefer_sentence:
            if sentence_end and not continuation and not incomplete:
                return True
            return topic_change and sentence_end and not continuation and not incomplete

        if sentence_end and not continuation and not incomplete:
            return True
        if topic_change and not continuation and not incomplete:
            return True

        soft_duration = min(max_duration, max(min_duration, (min_duration + max_duration) / 2))
        return duration >= soft_duration and not continuation and not incomplete

    @staticmethod
    def _is_sentence_boundary(text: str) -> bool:
        return bool(re.search(r'[。！？!?;；.]["”’）】》]*$', (text or '').strip()))

    @staticmethod
    def _starts_with_continuation(text: str) -> bool:
        normalized = (text or '').strip()
        return normalized.startswith((
            '然后', '接着', '同时', '而且', '并且', '以及', '还有',
            '所以', '因此', '因为', '但是', '不过', '然而', '比如', '例如', '也就是',
            '也就是说', '换句话说', '这时', '这就', '从而', '并', '和', '与', '或'
        ))

    @staticmethod
    def _ends_with_incomplete_phrase(text: str) -> bool:
        normalized = re.sub(r'\s+', '', text or '')
        if not normalized:
            return True
        if re.search(r'[，,、：:（(]$', normalized):
            return True
        return normalized.endswith((
            '的', '了', '和', '与', '及', '或', '在', '从', '到', '向', '给', '对',
            '把', '被', '将', '为', '以', '用', '让', '使', '是', '有', '没有',
            '一个', '一种', '这个', '那个', '这些', '那些', '通过', '关于'
        ))

    def _is_topic_change(self, old_keywords: List[str], new_keywords: List[str]) -> bool:
        old_set = {item for item in old_keywords if item}
        new_set = {item for item in new_keywords if item}
        if not old_set or not new_set:
            return False
        overlap = old_set & new_set
        if overlap:
            return False
        return len(overlap) / max(1, min(len(old_set), len(new_set))) < 0.25

    def _segment_keywords(self, text: str) -> List[str]:
        clean = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]+', ' ', text or '')
        hits = []
        for key in self.KEYWORD_TRANSLATIONS:
            if key in clean:
                hits.append(key)

        chinese_text = ''.join(re.findall(r'[\u4e00-\u9fff]+', clean))
        for size in (4, 3, 2):
            for start in range(0, max(0, len(chinese_text) - size + 1)):
                token = chinese_text[start:start + size]
                if token and token not in self.STOP_WORDS:
                    hits.append(token)

        for token in re.findall(r'[A-Za-z][A-Za-z0-9-]{2,}', clean):
            hits.append(token.lower())

        return self._merge_unique([], hits, limit=12)

    def _rebalance_short_segments(self, segments: List[Dict], min_duration: float, max_duration: float) -> List[Dict]:
        balanced = []
        for segment in segments:
            self._finalize_segment(segment)
            duration = float(segment.get('duration') or 0.0)
            if balanced and duration < min_duration:
                previous = balanced[-1]
                combined_duration = float(segment.get('end') or 0.0) - float(previous.get('start') or 0.0)
                source_complete = (
                    self._is_sentence_boundary(segment.get('text') or '') and
                    not self._starts_with_continuation(segment.get('text') or '')
                )
                previous_incomplete = self._ends_with_incomplete_phrase(previous.get('text') or '')
                if (not source_complete or previous_incomplete or duration < 1.2) and combined_duration <= max_duration * 1.25:
                    self._merge_segments(previous, segment)
                    continue
            balanced.append(segment)
        return balanced

    def _merge_segments(self, target: Dict, source: Dict):
        target['end'] = source.get('end') or target.get('end')
        target['text'] = f"{target.get('text') or ''} {source.get('text') or ''}".strip()
        target['subtitle_indices'] = (target.get('subtitle_indices') or []) + (source.get('subtitle_indices') or [])
        target['keywords'] = self._merge_unique(target.get('keywords') or [], source.get('keywords') or [], limit=10)
        self._finalize_segment(target)

    def _finalize_segment(self, segment: Dict):
        start = float(segment.get('start') or 0.0)
        end = max(start + 0.1, float(segment.get('end') or start + 0.1))
        text = str(segment.get('text') or '').strip()
        keywords = segment.get('keywords') or self._segment_keywords(text)
        segment['start'] = start
        segment['end'] = end
        segment['text'] = text
        segment['duration'] = round(end - start, 3)
        segment['keywords'] = self._merge_unique([], keywords, limit=6) or ['场景', '画面']
        segment['theme'] = '、'.join(segment['keywords'][:4])

    @staticmethod
    def _merge_unique(base: List[str], extra: List[str], limit: int = 6) -> List[str]:
        result = []
        for item in list(base or []) + list(extra or []):
            value = str(item or '').strip()
            if not value or value in result:
                continue
            result.append(value)
            if len(result) >= limit:
                break
        return result

    def _merge_short_subtitles(self, subtitles: List[Dict]) -> List[Dict]:
        result = []
        buffer = None
        for item in subtitles:
            start = float(item.get('start') or 0.0)
            end = max(start + 0.1, float(item.get('end') or 0.0))
            text = str(item.get('text') or '').strip()
            if not text:
                continue
            current = {'start': start, 'end': end, 'text': text}
            if buffer is None:
                buffer = current
            else:
                duration = buffer['end'] - buffer['start']
                if duration < 2.0 and current['start'] - buffer['end'] < 1.2:
                    buffer['end'] = current['end']
                    buffer['text'] = f"{buffer['text']} {current['text']}".strip()
                else:
                    result.extend(self._split_long_subtitle(buffer))
                    buffer = current
        if buffer:
            result.extend(self._split_long_subtitle(buffer))
        return result

    def _split_long_subtitle(self, item: Dict) -> List[Dict]:
        duration = item['end'] - item['start']
        if duration <= 8.0:
            return [item]
        pieces = max(1, int(duration // 6) + 1)
        piece_duration = duration / pieces
        return [{
            'start': item['start'] + index * piece_duration,
            'end': item['start'] + (index + 1) * piece_duration,
            'text': item['text']
        } for index in range(pieces)]

    def _extract_keywords(self, text: str, topic: str = '') -> List[str]:
        combined = f'{topic} {text}'.strip()
        hits = []
        for key in self.KEYWORD_TRANSLATIONS:
            if key in combined and key not in hits:
                hits.append(key)
        tokens = re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Za-z][A-Za-z0-9-]{2,}', combined)
        for token in tokens:
            if token in self.STOP_WORDS or token in hits:
                continue
            hits.append(token)
            if len(hits) >= 6:
                break
        return hits[:6] or ['场景', '画面']

    def _build_search_queries(self, keywords: List[str], text: str, topic: str = '') -> List[str]:
        translated = [self.KEYWORD_TRANSLATIONS.get(item) for item in keywords if self.KEYWORD_TRANSLATIONS.get(item)]
        queries = []
        if translated:
            queries.append(' '.join(translated[:3]))
        english_words = re.findall(r'[A-Za-z][A-Za-z0-9-]{2,}', f'{topic} {text}')
        if english_words:
            queries.append(' '.join(english_words[:5]))
        if not queries:
            queries.append(' '.join(translated[:2]) if translated else 'cinematic background')
        if 'cinematic background' not in queries:
            queries.append('cinematic background')
        return queries[:3]

    def _search_candidates_for_shot(self, shot: Dict, providers: List, orientation: str, max_candidates: int) -> List[Dict]:
        collected = []
        seen = set()
        queries = self._build_candidate_queries(shot)
        for query in queries[:2]:
            for provider in providers:
                try:
                    for candidate in provider.search(query, orientation=orientation, per_page=max_candidates):
                        key = (candidate.get('provider'), candidate.get('source_id'))
                        if key in seen:
                            continue
                        if not self._is_safe_candidate(candidate):
                            continue
                        seen.add(key)
                        candidate['score'] = self._score_candidate(candidate, shot)
                        collected.append(candidate)
                except ProviderError as e:
                    logger.warning(f'素材搜索失败: {provider.provider_id}, {query}, {e}')
                except Exception as e:
                    logger.warning(f'素材搜索异常: {provider.provider_id}, {query}, {e}')
        collected.sort(key=lambda item: item.get('score') or 0, reverse=True)
        return collected[:max_candidates]

    def _resolve_search_targets(self, data: Dict, shots: List[Dict]) -> List[str]:
        requested = data.get('shot_id') or data.get('shot_ids') or []
        if isinstance(requested, str):
            requested = [requested]
        if not isinstance(requested, list):
            requested = []
        target_ids = [str(item).strip() for item in requested if str(item).strip()]
        if not target_ids:
            return []
        available = {shot.get('shot_id') for shot in shots if shot.get('shot_id')}
        return [shot_id for shot_id in target_ids if shot_id in available]

    def _build_candidate_queries(self, shot: Dict) -> List[str]:
        queries = []
        text = str(shot.get('subtitle_text') or '')
        keywords = shot.get('keywords') or []
        combined = ' '.join([text] + [str(item) for item in keywords if item]).strip()

        if combined:
            query = self._sanitize_query(combined)
            if query and query not in queries:
                queries.append(query)

        if self._contains_news_topics(combined):
            for hint in self._news_hints(combined):
                if hint not in queries:
                    queries.append(hint)

        for query in shot.get('search_queries') or []:
            if query and query not in queries:
                queries.append(query)

        fallback = 'news footage'
        if fallback not in queries:
            queries.append(fallback)
        if 'cinematic background' not in queries:
            queries.append('cinematic background')
        return [query for query in queries if query]

    def _sanitize_query(self, text: str) -> str:
        pieces = []
        for token in re.split(r'[\s,，。！？!?;；:/\\]+', text or ''):
            value = token.strip()
            if not value:
                continue
            if any(bad.lower() in value.lower() for bad in self.SAFE_CONTENT_BLACKLIST):
                continue
            pieces.append(value)
        return ' '.join(pieces[:6]).strip()

    def _contains_news_topics(self, text: str) -> bool:
        keywords = {'政治', '时政', '外交', '军事', '国防', '军队', '会议', '新闻', '发布会'}
        return any(word in (text or '') for word in keywords)

    def _news_hints(self, text: str) -> List[str]:
        hints = []
        for keyword, values in self.NEWS_TOPIC_HINTS.items():
            if keyword in (text or ''):
                hints.extend(values)
        return self._merge_unique([], hints, limit=4)

    def _candidate_text(self, candidate: Dict) -> str:
        parts = [
            candidate.get('title') or '',
            candidate.get('description') or '',
            candidate.get('source_id') or '',
            candidate.get('source_url') or '',
            candidate.get('author') or '',
            candidate.get('license') or '',
            candidate.get('query') or ''
        ]
        return ' '.join(str(part) for part in parts if part)

    def _is_safe_candidate(self, candidate: Dict) -> bool:
        text = self._candidate_text(candidate).lower()
        if not text:
            return True
        for bad in self.SAFE_CONTENT_BLACKLIST:
            if bad.lower() in text:
                return False
        return True

    def _score_candidate(self, candidate: Dict, shot: Dict) -> int:
        score = 40
        duration = float(candidate.get('duration') or 0.0)
        shot_duration = float(shot.get('duration') or 0.0)
        if duration >= shot_duration:
            score += 20
        elif duration > 0:
            score += 8
        width = int(candidate.get('width') or 0)
        height = int(candidate.get('height') or 0)
        if width >= 1280 and height >= 720:
            score += 18
        elif width >= 720:
            score += 10
        if width >= height:
            score += 8
        if candidate.get('provider') in {'wikimedia', 'nasa', 'internet_archive'}:
            score += 6
        if candidate.get('provider') == 'pexels':
            score += 4
        candidate_text = self._candidate_text(candidate).lower()
        if any(keyword in candidate_text for keyword in ('news', 'report', 'press', 'government', 'military', 'defense')):
            score += 8
        return score

    def _ensure_compose_assets(self, project_id: str, shots: List[Dict], task_id: str = '') -> Dict:
        """合成前确保已选候选素材有本地文件，避免自动合成退回原视频。"""
        target_shots = [shot for shot in shots or [] if not shot.get('skipped') and (shot.get('candidates') or [])]
        downloaded = 0
        usable = 0
        failed_shots = 0
        failed_candidates = 0
        for index, shot in enumerate(target_shots, start=1):
            if task_id:
                progress = 6 + int(index / max(1, len(target_shots)) * 18)
                self._task_update(task_id, 'running', progress, {
                    'message': f'正在下载合成素材 {index}/{len(target_shots)}',
                    'shots': shots
                })
            prepared = False
            for candidate in self._compose_candidate_options(shot):
                if self._candidate_has_local_file(candidate):
                    shot['selected_candidate_id'] = candidate.get('candidate_id') or shot.get('selected_candidate_id') or ''
                    candidate.pop('download_error', None)
                    usable += 1
                    prepared = True
                    break
                try:
                    local_path = self._download_candidate(candidate)
                    candidate['local_path'] = local_path
                    candidate.pop('download_error', None)
                    shot['selected_candidate_id'] = candidate.get('candidate_id') or shot.get('selected_candidate_id') or ''
                    self._register_material(project_id, shot, candidate, local_path)
                    downloaded += 1
                    usable += 1
                    prepared = True
                    break
                except Exception as e:
                    failed_candidates += 1
                    candidate['download_error'] = str(e)
                    logger.warning(
                        f"合成前下载补画面素材失败: shot={shot.get('shot_id')}, "
                        f"provider={candidate.get('provider')}, source_id={candidate.get('source_id')}, {e}"
                    )
            if not prepared:
                failed_shots += 1
        return {'downloaded': downloaded, 'usable': usable, 'failed': failed_shots, 'failed_candidates': failed_candidates}

    def _compose_candidate_options(self, shot: Dict) -> List[Dict]:
        candidates = list(shot.get('candidates') or [])
        selected_id = shot.get('selected_candidate_id') or ''
        ordered = []
        if selected_id:
            selected = next((candidate for candidate in candidates if candidate.get('candidate_id') == selected_id), None)
            if selected:
                ordered.append(selected)
        for candidate in candidates:
            if candidate not in ordered:
                ordered.append(candidate)
        return ordered

    def _candidate_has_local_file(self, candidate: Dict) -> bool:
        local_path = candidate.get('local_path') or ''
        if not local_path:
            return False
        path = Path(str(local_path))
        if not path.is_absolute():
            path = PROJECT_ROOT / str(local_path).lstrip('/\\')
        return path.exists() and path.stat().st_size > 0

    def _download_candidate(self, candidate: Dict) -> str:
        url = candidate.get('download_url') or ''
        if not url:
            raise ValueError('候选素材缺少下载地址')
        ext = Path(urlparse(url).path).suffix.lower()
        if ext not in {'.mp4', '.mov', '.m4v', '.webm'}:
            ext = '.mp4'
        filename = f"{candidate.get('provider')}_{candidate.get('source_id')}_{candidate.get('quality') or 'video'}{ext}"
        target = self.cache_dir / self._safe_filename(filename)
        if target.exists() and target.stat().st_size > 0:
            return self._relative_path(target)

        request = Request(url, headers={'User-Agent': 'JJYB-AI-Video/1.0'})
        with urlopen(request, timeout=int(self._stock_config().get('request_timeout_seconds') or 20)) as response:
            with target.open('wb') as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
        if target.stat().st_size <= 0:
            target.unlink(missing_ok=True)
            raise RuntimeError('素材下载结果为空')
        return self._relative_path(target)

    def _register_material(self, project_id: str, shot: Dict, candidate: Dict, local_path: str):
        project = self.db_manager.get_project(project_id) or {}
        for material in project.get('materials') or []:
            if material.get('path') == local_path:
                return
        abs_path = PROJECT_ROOT / local_path
        metadata = {
            'source': 'broll_stock_video',
            'shot_id': shot.get('shot_id') or '',
            'provider': candidate.get('provider') or '',
            'source_id': candidate.get('source_id') or '',
            'source_url': candidate.get('source_url') or '',
            'author': candidate.get('author') or '',
            'license': candidate.get('license') or '',
            'license_url': candidate.get('license_url') or '',
            'download_url': candidate.get('download_url') or '',
            'local_path': local_path,
            'query': candidate.get('query') or ''
        }
        self.db_manager.create_material(
            project_id=project_id,
            material_type='video',
            name=f"B-roll {candidate.get('provider')}-{candidate.get('source_id')}",
            path=local_path,
            size=abs_path.stat().st_size if abs_path.exists() else 0,
            duration=float(candidate.get('duration') or 0.0),
            metadata=metadata
        )

    def _selected_candidate(self, shot: Dict) -> Optional[Dict]:
        candidates = shot.get('candidates') or []
        selected_id = shot.get('selected_candidate_id') or ''
        if selected_id:
            for candidate in candidates:
                if candidate.get('candidate_id') == selected_id:
                    return candidate
        return candidates[0] if candidates else None

    def _build_providers(self) -> Dict:
        config = self._stock_config()
        api_config = {}
        try:
            api_config = self.db_manager.get_api_config() or {}
        except Exception:
            api_config = {}
        timeout = int(config.get('request_timeout_seconds') or 20)
        pexels_key = (
            config.get('pexels_api_key') or
            api_config.get('pexels_api_key') or
            api_config.get('pexels_key') or
            os.getenv('PEXELS_API_KEY') or
            ''
        )
        pixabay_key = (
            config.get('pixabay_api_key') or
            api_config.get('pixabay_api_key') or
            api_config.get('pixabay_key') or
            os.getenv('PIXABAY_API_KEY') or
            ''
        )
        return {
            'wikimedia': WikimediaCommonsProvider(timeout=timeout),
            'internet_archive': InternetArchiveProvider(timeout=timeout),
            'nasa': NasaVideoProvider(timeout=timeout),
            'videvo': VidevoProvider(timeout=timeout),
            'videezy': VideezyProvider(timeout=timeout),
            'mazwai': MazwaiProvider(timeout=timeout),
            'lifeofvids': LifeOfVidsProvider(timeout=timeout),
            'splitshire': SplitshireProvider(timeout=timeout),
            'coverr': CoverrProvider(timeout=timeout),
            'pexels': PexelsProvider(pexels_key, timeout=timeout),
            'pixabay': PixabayProvider(pixabay_key, timeout=timeout)
        }

    def _stock_config(self) -> Dict:
        settings = {}
        try:
            settings = self.db_manager.get_settings() or {}
        except Exception:
            settings = {}
        stock = settings.get('stock_video') if isinstance(settings, dict) else {}
        if not isinstance(stock, dict):
            stock = {}
        merged = dict(self.DEFAULT_CONFIG)
        merged.update(stock)
        for key in ('pexels_api_key', 'pixabay_api_key'):
            if key in settings and key not in merged:
                merged[key] = settings.get(key)
        return merged

    def _get_subtitles(self, project: Dict, data: Dict) -> List[Dict]:
        if isinstance(data.get('subtitles'), list):
            return self._normalize_subtitles(data.get('subtitles'))
        session = self._subtitle_session(project)
        subtitles = self._normalize_subtitles(session.get('subtitles') or [])
        if subtitles:
            return subtitles
        for task in project.get('tasks') or []:
            if task.get('type') != 'subtitle_generate' or task.get('status') != 'completed':
                continue
            output = task.get('output_data') or {}
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except Exception:
                    output = {}
            subtitles = self._normalize_subtitles(output.get('subtitles') or [])
            if subtitles:
                return subtitles
        return []

    def _get_subtitle_style(self, project: Dict, data: Dict) -> Dict:
        if isinstance(data.get('style'), dict):
            return data.get('style') or {}
        return self._subtitle_session(project).get('style') or {}

    def _normalize_subtitles(self, raw: List[Dict]) -> List[Dict]:
        subtitles = []
        for item in raw or []:
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

    @staticmethod
    def _project_result(project: Dict) -> Dict:
        result = (project or {}).get('result') or {}
        if isinstance(result, dict):
            return dict(result)
        try:
            parsed = json.loads(result)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _subtitle_session(self, project: Dict) -> Dict:
        session = self._project_result(project).get('subtitle_session') or {}
        return session if isinstance(session, dict) else {}

    @staticmethod
    def _find_video_material(materials: List[Dict]) -> Optional[Dict]:
        for material in materials or []:
            if material.get('type') == 'video' and material.get('path'):
                return material
        return None

    def _task_update(self, task_id: str, status: str, progress=None, output_data=None, error_message=None):
        try:
            if progress is not None:
                self.db_manager.update_task_progress(task_id, float(progress))
            self.db_manager.update_task_status(task_id, status, output_data=output_data, error_message=error_message)
            if self.socketio:
                payload = {'task_id': task_id, 'status': status}
                if progress is not None:
                    payload['progress'] = float(progress)
                if error_message:
                    payload['error'] = error_message
                self.socketio.emit('task_status', payload)
        except Exception as e:
            logger.warning(f'更新补画面任务状态失败: {task_id}, {e}')

    def _update_project_status(self, project_id: str, status: str):
        try:
            self.db_manager.update_project(project_id, {'status': status})
        except Exception as e:
            logger.warning(f'更新补画面项目状态失败: {project_id}, {status}, {e}')

    @staticmethod
    def _task_name(task_type: str) -> str:
        return {
            'broll_plan': '生成补画面方案',
            'broll_search': '搜索补画面素材',
            'broll_download': '下载补画面素材',
            'broll_compose': '合成补画面视频'
        }.get(task_type, '补画面任务')

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r'[^A-Za-z0-9._-]+', '_', value or 'stock_video.mp4')

    @staticmethod
    def _relative_path(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(PROJECT_ROOT)).replace('\\', '/')
        except Exception:
            return str(path).replace('\\', '/')
