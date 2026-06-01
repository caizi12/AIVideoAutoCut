# -*- coding: utf-8 -*-
"""Coverr 免费视频素材 Provider。"""

import re
from typing import Dict, List
from urllib.parse import urlencode

from .base_provider import StockVideoProvider


class CoverrProvider(StockVideoProvider):
    """基于 Coverr 网站搜索免费视频素材，无需 API Key。

    Coverr 提供精美的免费视频素材，专注于网站背景视频。
    网站: https://coverr.co/
    许可: CC0 (Public Domain)，免费用于个人和商业用途
    """

    provider_id = 'coverr'
    display_name = 'Coverr'
    license_name = 'CC0 Public Domain'
    license_url = 'https://creativecommons.org/publicdomain/zero/1.0/'
    requires_api_key = False
    base_url = 'https://coverr.co'
    search_url = 'https://coverr.co/search'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        """搜索 Coverr 免费视频素材。

        注意：Coverr 没有公开 API，此实现通过解析搜索页面获取视频信息。
        """
        try:
            # 构建搜索URL
            url = f'{self.search_url}?q={query}'

            html = self._get_html(url)
            if not html:
                return []

            # 解析视频列表
            candidates = self._parse_search_results(html, query)
            return candidates[:per_page]

        except Exception as e:
            import logging
            logging.warning(f'Coverr 搜索失败: {query}, {e}')
            return []

    def _get_html(self, url: str) -> str:
        """获取网页HTML内容。"""
        from urllib.request import Request, urlopen

        request = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        try:
            with urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or 'utf-8'
                return response.read().decode(charset, errors='replace')
        except Exception:
            return ''

    def _parse_search_results(self, html: str, query: str) -> List[Dict]:
        """解析搜索结果页面，提取视频信息。"""
        candidates = []

        # Coverr 的视频链接通常是 /videos/video-name
        video_pattern = r'<a[^>]*href="(/videos/[^"]+)"[^>]*>.*?<img[^>]*src="([^"]+)"'
        matches = re.findall(video_pattern, html, re.DOTALL)

        for idx, (video_path, thumbnail) in enumerate(matches[:12]):
            try:
                # 构建完整URL
                video_url = f'{self.base_url}{video_path}'

                # 提取视频ID
                video_id = video_path.strip('/').split('/')[-1]
                title = video_id.replace('-', ' ').title()

                # 处理缩略图URL
                if not thumbnail.startswith('http'):
                    thumbnail = f'{self.base_url}{thumbnail}' if thumbnail.startswith('/') else thumbnail

                candidate = {
                    'candidate_id': f'coverr_{video_id}',
                    'provider': self.provider_id,
                    'source_id': video_id,
                    'title': title,
                    'description': title,
                    'source_url': video_url,
                    'author': 'Coverr',
                    'license': self.license_name,
                    'license_url': self.license_url,
                    'download_url': video_url,  # 需要访问详情页获取实际下载链接
                    'width': 1920,
                    'height': 1080,
                    'duration': 0,
                    'fps': 30,
                    'query': query,
                    'quality': 'hd',
                    'local_path': '',
                    'score': 0,
                    'thumbnail': thumbnail
                }
                candidates.append(candidate)
            except Exception:
                continue

        return candidates

    def get_download_url(self, video_url: str) -> str:
        """从视频详情页获取实际下载链接。

        Args:
            video_url: 视频详情页URL

        Returns:
            实际的视频下载URL
        """
        try:
            html = self._get_html(video_url)
            if not html:
                return ''

            # 方案1: 查找下载按钮
            download_pattern = r'<a[^>]*href="([^"]+\.mp4[^"]*)"[^>]*download'
            match = re.search(download_pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            # 方案2: video 标签中的 source
            video_source_pattern = r'<source[^>]*src="([^"]+\.mp4[^"]*)"'
            match = re.search(video_source_pattern, html)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            # 方案3: data-video-url 属性
            data_video_pattern = r'data-video-url="([^"]+)"'
            match = re.search(data_video_pattern, html)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            # 方案4: 直接的 .mp4 链接
            mp4_pattern = r'"(https://[^"]*coverr[^"]*\.mp4[^"]*)"'
            match = re.search(mp4_pattern, html)
            if match:
                return match.group(1)

            return ''
        except Exception:
            return ''
