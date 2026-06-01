# -*- coding: utf-8 -*-
"""NASA Image and Video Library 素材 Provider。"""

from typing import Dict, List
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from .base_provider import StockVideoProvider


class NasaVideoProvider(StockVideoProvider):
    """基于 NASA Image and Video Library 搜索公开视频，无需 API Key。"""

    provider_id = 'nasa'
    display_name = 'NASA Image and Video Library'
    license_name = 'NASA Media Usage Guidelines'
    license_url = 'https://www.nasa.gov/nasa-brand-center/images-and-media/'
    requires_api_key = False
    endpoint = 'https://images-api.nasa.gov/search'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        params = {
            'q': query,
            'media_type': 'video',
            'page_size': max(1, min(int(per_page or 6), 10))
        }
        data = self._get_json(
            f'{self.endpoint}?{urlencode(params)}',
            headers={'User-Agent': 'JJYB-AI-Video/1.0'}
        )
        items = (((data or {}).get('collection') or {}).get('items') or [])
        candidates = []
        for item in items:
            candidate = self._normalize_item(item, query)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _normalize_item(self, item: Dict, query: str) -> Dict:
        data = (item.get('data') or [{}])[0] or {}
        nasa_id = str(data.get('nasa_id') or '').strip()
        if not nasa_id:
            return {}
        asset_urls = self._get_asset_urls(item.get('href') or '')
        video_url = self._choose_video_url(asset_urls)
        if not video_url:
            return {}
        links = item.get('links') or []
        source_url = f'https://images.nasa.gov/details/{quote(nasa_id)}'
        author = data.get('photographer') or data.get('center') or 'NASA'

        return {
            'candidate_id': f'nasa_{nasa_id}',
            'provider': self.provider_id,
            'source_id': nasa_id,
            'title': data.get('title') or nasa_id,
            'description': data.get('description') or '',
            'source_url': source_url,
            'author': author,
            'license': self.license_name,
            'license_url': self.license_url,
            'download_url': video_url,
            'width': self._link_int(links, 'width'),
            'height': self._link_int(links, 'height'),
            'duration': 0,
            'fps': 0,
            'query': query,
            'quality': self._quality(video_url),
            'local_path': '',
            'score': 0
        }

    def _get_asset_urls(self, href: str) -> List[str]:
        if not href:
            return []
        safe_href = self._safe_url(href)
        data = self._get_json(safe_href, headers={'User-Agent': 'JJYB-AI-Video/1.0'})
        return data if isinstance(data, list) else []

    @staticmethod
    def _choose_video_url(urls: List[str]) -> str:
        videos = [url for url in urls or [] if str(url).lower().split('?', 1)[0].endswith(('.mp4', '.mov', '.m4v', '.webm'))]
        if not videos:
            return ''
        order = ['~large.mp4', '~medium.mp4', '~orig.mp4', '~small.mp4', '.mp4']
        for suffix in order:
            for url in videos:
                if suffix in url.lower():
                    return url
        return videos[0]

    @staticmethod
    def _quality(url: str) -> str:
        lower = str(url or '').lower()
        for key in ('orig', 'large', 'medium', 'small', 'preview', 'mobile'):
            if f'~{key}' in lower:
                return key
        return 'video'

    @staticmethod
    def _link_int(links: List[Dict], key: str) -> int:
        for item in links or []:
            if key in item:
                try:
                    return int(item.get(key) or 0)
                except Exception:
                    return 0
        return 0

    @staticmethod
    def _safe_url(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, quote(parts.path), parts.query, parts.fragment))
