# -*- coding: utf-8 -*-
"""Pexels 视频素材 Provider。"""

from typing import Dict, List
from urllib.parse import urlencode

from .base_provider import ProviderError, StockVideoProvider


class PexelsProvider(StockVideoProvider):
    """基于 Pexels 官方 Videos Search API 搜索公开视频。"""

    provider_id = 'pexels'
    display_name = 'Pexels'
    license_name = 'Pexels License'
    license_url = 'https://www.pexels.com/license/'
    endpoint = 'https://api.pexels.com/v1/videos/search'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        if not self.available:
            raise ProviderError('Pexels API Key 未配置')

        params = {
            'query': query,
            'per_page': max(1, min(int(per_page or 6), 15)),
            'orientation': orientation or 'landscape'
        }
        data = self._get_json(
            f'{self.endpoint}?{urlencode(params)}',
            headers={'Authorization': self.api_key}
        )
        videos = data.get('videos') if isinstance(data, dict) else []
        candidates = []
        for item in videos or []:
            candidate = self._normalize_video(item, query)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _normalize_video(self, item: Dict, query: str) -> Dict:
        source_id = str(item.get('id') or '').strip()
        if not source_id:
            return {}

        files = item.get('video_files') or []
        chosen = self._choose_file(files)
        if not chosen:
            return {}

        width = self._safe_int(chosen.get('width') or item.get('width'))
        height = self._safe_int(chosen.get('height') or item.get('height'))
        duration = self._safe_float(item.get('duration'))
        fps = self._safe_float(chosen.get('fps'))
        user = item.get('user') or {}

        return {
            'candidate_id': f'pexels_{source_id}',
            'provider': self.provider_id,
            'source_id': source_id,
            'source_url': item.get('url') or '',
            'author': user.get('name') or '',
            'license': self.license_name,
            'license_url': self.license_url,
            'download_url': chosen.get('link') or '',
            'width': width,
            'height': height,
            'duration': duration,
            'fps': fps,
            'query': query,
            'quality': chosen.get('quality') or '',
            'local_path': '',
            'score': 0
        }

    def _choose_file(self, files: List[Dict]) -> Dict:
        valid = [f for f in files or [] if f.get('link')]
        if not valid:
            return {}

        def rank(file_item):
            width = self._safe_int(file_item.get('width'))
            height = self._safe_int(file_item.get('height'))
            pixels = width * height
            quality = str(file_item.get('quality') or '').lower()
            quality_rank = {'uhd': 4, 'hd': 3, 'sd': 2}.get(quality, 1)
            return (quality_rank, min(pixels, 1920 * 1080))

        return sorted(valid, key=rank, reverse=True)[0]
