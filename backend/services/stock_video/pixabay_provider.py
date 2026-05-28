# -*- coding: utf-8 -*-
"""Pixabay 视频素材 Provider。"""

from typing import Dict, List
from urllib.parse import urlencode

from .base_provider import ProviderError, StockVideoProvider


class PixabayProvider(StockVideoProvider):
    """基于 Pixabay 官方 Videos API 搜索公开视频。"""

    provider_id = 'pixabay'
    display_name = 'Pixabay'
    license_name = 'Pixabay Content License'
    license_url = 'https://pixabay.com/service/license-summary/'
    endpoint = 'https://pixabay.com/api/videos/'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        if not self.available:
            raise ProviderError('Pixabay API Key 未配置')

        params = {
            'key': self.api_key,
            'q': query,
            'per_page': max(3, min(int(per_page or 6), 20)),
            'safesearch': 'true',
            'video_type': 'all'
        }
        data = self._get_json(f'{self.endpoint}?{urlencode(params)}')
        hits = data.get('hits') if isinstance(data, dict) else []
        candidates = []
        for item in hits or []:
            candidate = self._normalize_video(item, query)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _normalize_video(self, item: Dict, query: str) -> Dict:
        source_id = str(item.get('id') or '').strip()
        if not source_id:
            return {}

        chosen = self._choose_file(item.get('videos') or {})
        if not chosen:
            return {}

        width = self._safe_int(chosen.get('width'))
        height = self._safe_int(chosen.get('height'))
        duration = self._safe_float(item.get('duration'))

        return {
            'candidate_id': f'pixabay_{source_id}',
            'provider': self.provider_id,
            'source_id': source_id,
            'source_url': item.get('pageURL') or '',
            'author': item.get('user') or '',
            'license': self.license_name,
            'license_url': self.license_url,
            'download_url': chosen.get('url') or '',
            'width': width,
            'height': height,
            'duration': duration,
            'fps': 0,
            'query': query,
            'quality': chosen.get('quality') or '',
            'local_path': '',
            'score': 0
        }

    def _choose_file(self, videos: Dict) -> Dict:
        order = ['large', 'medium', 'small', 'tiny']
        for quality in order:
            item = videos.get(quality)
            if item and item.get('url'):
                chosen = dict(item)
                chosen['quality'] = quality
                return chosen
        return {}
