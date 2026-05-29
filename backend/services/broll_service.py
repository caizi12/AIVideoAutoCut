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
        'max_candidates_per_shot': 6,
        'max_download_mb_per_project': 2048,
        'cache_days': 14,
        'request_timeout_seconds': 12,
        'prefer_orientation': 'landscape'
    }

    STOP_WORDS = {
        '这个', '那个', '我们', '你们', '他们', '它们', '一个', '一种', '因为', '所以', '如果', '但是',
        '然后', '就是', '可以', '没有', '不是', '正在', '开始', '时候', '通过', '这些', '那些'
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
                'prefer_sentence_boundary': data.get('prefer_sentence_boundary', False),
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

            providers = self._build_providers()
            enabled_names = data.get('providers') or session.get('providers') or list(self.DEFAULT_CONFIG['providers'])
            enabled = [providers[name] for name in enabled_names if name in providers and providers[name].available]
            if not enabled:
                raise ValueError('没有可用素材源。免 Key 素材源不可用，或已被配置关闭；请检查网络后重试')

            max_candidates = int(self._stock_config().get('max_candidates_per_shot') or 6)
            orientation = self._stock_config().get('prefer_orientation') or 'landscape'

            for index, shot in enumerate(shots, start=1):
                if shot.get('locked') and shot.get('candidates'):
                    continue
                progress = 5 + int(index / max(1, len(shots)) * 85)
                self._task_update(task_id, 'running', progress, {
                    'message': f'正在搜索镜头素材 {index}/{len(shots)}',
                    'shots': shots
                })
                candidates = self._search_candidates_for_shot(shot, enabled, orientation, max_candidates)
                shot['candidates'] = candidates
                if candidates and not shot.get('selected_candidate_id'):
                    shot['selected_candidate_id'] = candidates[0]['candidate_id']

            session['shots'] = shots
            session['updated_at'] = datetime.now().isoformat(timespec='seconds')
            saved = self.save_session(project_id, session)
            output = {
                'message': '素材候选搜索完成',
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

            composer = BrollComposer()

            def progress(value, message):
                self._task_update(task_id, 'running', value, {
                    'message': message,
                    'broll_session': session
                })

            self._task_update(task_id, 'running', 5, {'message': '正在准备补画面合成'})
            result = composer.compose(
                project_id=project_id,
                source_video_path=source_video_path,
                shots=session.get('shots') or [],
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
            output = {
                'message': '补画面视频合成完成',
                'output_url': result.get('output_url') or '',
                'output_path': result.get('output_path') or '',
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
        merged = self._merge_short_subtitles(subtitles)
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
                'keywords': keywords,
                'search_queries': search_queries,
                'locked': False,
                'skipped': False,
                'selected_candidate_id': '',
                'candidates': []
            })
        return shots

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
        queries = shot.get('search_queries') or ['cinematic background']
        for query in queries[:2]:
            for provider in providers:
                try:
                    for candidate in provider.search(query, orientation=orientation, per_page=max_candidates):
                        key = (candidate.get('provider'), candidate.get('source_id'))
                        if key in seen:
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
        if candidate.get('provider') in {'wikimedia', 'nasa'}:
            score += 6
        if candidate.get('provider') == 'pexels':
            score += 4
        return score

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
