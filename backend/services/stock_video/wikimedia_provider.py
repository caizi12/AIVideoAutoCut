# -*- coding: utf-8 -*-
"""Wikimedia Commons 公开视频素材 Provider。"""

from typing import Dict, List
from urllib.parse import urlencode

from .base_provider import StockVideoProvider


class WikimediaCommonsProvider(StockVideoProvider):
    """基于 Wikimedia Commons API 搜索公开视频文件，无需 API Key。"""

    provider_id = 'wikimedia'
    display_name = 'Wikimedia Commons'
    license_name = 'Wikimedia Commons 文件页许可'
    license_url = 'https://commons.wikimedia.org/wiki/Commons:Licensing'
    requires_api_key = False
    endpoint = 'https://commons.wikimedia.org/w/api.php'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        params = {
            'action': 'query',
            'generator': 'search',
            'gsrnamespace': '6',
            'gsrsearch': f'{query} filetype:video',
            'gsrlimit': max(1, min(int(per_page or 6), 12)),
            'prop': 'imageinfo',
            'iiprop': 'url|mime|size|metadata|extmetadata',
            'format': 'json',
            'formatversion': '2'
        }
        data = self._get_json(
            f'{self.endpoint}?{urlencode(params)}',
            headers={'User-Agent': 'JJYB-AI-Video/1.0'}
        )
        pages = ((data or {}).get('query') or {}).get('pages') or []
        candidates = []
        for page in pages:
            candidate = self._normalize_page(page, query)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _normalize_page(self, page: Dict, query: str) -> Dict:
        info = (page.get('imageinfo') or [{}])[0] or {}
        mime = str(info.get('mime') or '').lower()
        url = info.get('url') or ''
        if not url or not mime.startswith('video/'):
            return {}

        ext = self._extmetadata(info.get('extmetadata') or {})
        source_id = str(page.get('pageid') or page.get('title') or '').strip()
        license_name = ext.get('LicenseShortName') or ext.get('UsageTerms') or self.license_name
        license_url = ext.get('LicenseUrl') or self.license_url
        author = self._strip_html(ext.get('Artist') or ext.get('Credit') or '')

        return {
            'candidate_id': f'wikimedia_{source_id}',
            'provider': self.provider_id,
            'source_id': source_id,
            'title': page.get('title') or source_id,
            'description': self._strip_html(ext.get('ImageDescription') or ext.get('ObjectName') or ''),
            'source_url': info.get('descriptionurl') or '',
            'author': author,
            'license': self._strip_html(license_name),
            'license_url': license_url,
            'download_url': url,
            'width': self._safe_int(info.get('width')),
            'height': self._safe_int(info.get('height')),
            'duration': self._safe_float(info.get('duration')),
            'fps': self._metadata_number(info.get('metadata') or [], {'frame_rate', 'framerate'}),
            'query': query,
            'quality': 'original',
            'local_path': '',
            'score': 0
        }

    @staticmethod
    def _extmetadata(data: Dict) -> Dict:
        result = {}
        for key, item in (data or {}).items():
            if isinstance(item, dict):
                result[key] = item.get('value') or ''
            else:
                result[key] = item or ''
        return result

    @classmethod
    def _metadata_number(cls, items: List[Dict], names) -> float:
        for item in items or []:
            name = str(item.get('name') or '').lower()
            if name in names:
                return cls._safe_float(item.get('value'))
            value = item.get('value')
            if isinstance(value, list):
                found = cls._metadata_number(value, names)
                if found:
                    return found
        return 0.0

    @staticmethod
    def _strip_html(value: str) -> str:
        import re
        return re.sub(r'<[^>]+>', '', str(value or '')).strip()
