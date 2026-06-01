# -*- coding: utf-8 -*-
"""Internet Archive 公开视频素材 Provider。"""

from typing import Dict, List
from urllib.parse import quote, urlencode

from .base_provider import StockVideoProvider


class InternetArchiveProvider(StockVideoProvider):
    """基于 Internet Archive Advanced Search / Metadata API 搜索公开视频。"""

    provider_id = 'internet_archive'
    display_name = 'Internet Archive'
    license_name = 'Internet Archive 条目页许可'
    license_url = 'https://archive.org/about/terms.php'
    requires_api_key = False
    search_endpoint = 'https://archive.org/advancedsearch.php'
    metadata_endpoint = 'https://archive.org/metadata'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        params = {
            'q': f'{query} AND mediatype:movies AND (licenseurl:* OR rights:"Public Domain")',
            'rows': max(1, min(int(per_page or 6), 10)),
            'output': 'json',
            'fl[]': ['identifier', 'title', 'creator', 'licenseurl', 'rights']
        }
        data = self._get_json(
            f'{self.search_endpoint}?{urlencode(params, doseq=True)}',
            headers={'User-Agent': 'JJYB-AI-Video/1.0'}
        )
        docs = ((data or {}).get('response') or {}).get('docs') or []
        candidates = []
        for item in docs:
            candidate = self._normalize_doc(item, query)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _normalize_doc(self, item: Dict, query: str) -> Dict:
        identifier = str(item.get('identifier') or '').strip()
        if not identifier:
            return {}
        license_url = str(item.get('licenseurl') or '').strip()
        rights = str(item.get('rights') or '').strip()
        if not self._is_usable_license(license_url, rights):
            return {}

        metadata = self._get_json(
            f'{self.metadata_endpoint}/{quote(identifier)}',
            headers={'User-Agent': 'JJYB-AI-Video/1.0'}
        )
        file_item = self._choose_file(metadata.get('files') or [])
        if not file_item:
            return {}

        meta = metadata.get('metadata') or {}
        duration = self._parse_runtime(meta.get('runtime') or file_item.get('length') or file_item.get('mtime'))
        filename = file_item.get('name') or ''
        download_url = f'https://archive.org/download/{quote(identifier)}/{quote(filename)}'
        license_name = self._license_name(license_url, rights)

        return {
            'candidate_id': f'internet_archive_{identifier}',
            'provider': self.provider_id,
            'source_id': identifier,
            'title': self._as_text(meta.get('title') or item.get('title') or identifier),
            'description': self._as_text(meta.get('description') or meta.get('subject') or ''),
            'source_url': f'https://archive.org/details/{identifier}',
            'author': self._as_text(meta.get('creator') or item.get('creator') or ''),
            'license': license_name,
            'license_url': license_url or self.license_url,
            'download_url': download_url,
            'width': self._safe_int(file_item.get('width')),
            'height': self._safe_int(file_item.get('height')),
            'duration': duration,
            'fps': 0,
            'query': query,
            'quality': file_item.get('format') or 'video',
            'local_path': '',
            'score': 0
        }

    def _choose_file(self, files: List[Dict]) -> Dict:
        video_exts = ('.mp4', '.webm', '.ogv', '.mov', '.m4v')
        candidates = []
        for item in files or []:
            name = str(item.get('name') or '')
            if name.lower().endswith(video_exts):
                candidates.append(item)
        if not candidates:
            return {}

        def rank(item):
            name = str(item.get('name') or '').lower()
            fmt = str(item.get('format') or '').lower()
            size = self._safe_int(item.get('size'))
            mp4_rank = 2 if name.endswith('.mp4') or 'h.264' in fmt else 1
            return (mp4_rank, min(size, 300 * 1024 * 1024))

        return sorted(candidates, key=rank, reverse=True)[0]

    @staticmethod
    def _is_usable_license(license_url: str, rights: str) -> bool:
        text = f'{license_url} {rights}'.lower()
        if 'public domain' in text or 'creativecommons.org/publicdomain' in text:
            return True
        if 'creativecommons.org/licenses/by/' in text:
            return True
        if 'creativecommons.org/licenses/by-sa/' in text:
            return True
        return False

    @staticmethod
    def _license_name(license_url: str, rights: str) -> str:
        text = f'{license_url} {rights}'.lower()
        if 'public domain' in text:
            return 'Public Domain'
        if 'by-sa' in text:
            return 'Creative Commons BY-SA'
        if 'creativecommons.org/licenses/by/' in text:
            return 'Creative Commons BY'
        return rights or 'Internet Archive 条目页许可'

    @classmethod
    def _parse_runtime(cls, value) -> float:
        text = str(value or '').strip()
        if not text:
            return 0.0
        if ':' in text:
            parts = [cls._safe_float(part) for part in text.split(':')]
            total = 0.0
            for part in parts:
                total = total * 60 + part
            return total
        return cls._safe_float(text)

    @staticmethod
    def _as_text(value) -> str:
        if isinstance(value, list):
            return ', '.join(str(item) for item in value if item)
        return str(value or '')
