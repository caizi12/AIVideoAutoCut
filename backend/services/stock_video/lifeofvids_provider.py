# -*- coding: utf-8 -*-
"""Life of Vids 免费视频素材 Provider。"""

import re
from typing import Dict, List

from .base_provider import StockVideoProvider


class LifeOfVidsProvider(StockVideoProvider):
    """基于 Life of Vids 网站搜索免费视频素材，无需 API Key。

    Life of Vids 提供生活类高质量免费视频素材。
    网站: https://www.lifeofvids.com/
    许可: CC0 (Public Domain)，无需注明出处
    """

    provider_id = 'lifeofvids'
    display_name = 'Life of Vids'
    license_name = 'CC0 Public Domain'
    license_url = 'https://creativecommons.org/publicdomain/zero/1.0/'
    requires_api_key = False
    base_url = 'https://www.lifeofvids.com'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        """搜索 Life of Vids 免费视频素材。

        注意：Life of Vids 没有公开搜索 API，此实现通过解析视频页面获取内容。
        """
        try:
            # Life of Vids 的视频页面
            url = f'{self.base_url}/videos/'

            html = self._get_html(url)
            if not html:
                return []

            # 解析视频列表
            candidates = self._parse_video_list(html, query)

            # 根据查询词过滤
            if query:
                query_lower = query.lower()
                filtered = []
                for c in candidates:
                    # 检查标题、URL或作者中是否包含关键词
                    searchable = f"{c.get('source_url', '')} {c.get('author', '')}".lower()
                    if any(word in searchable for word in query_lower.split()):
                        filtered.append(c)
                if filtered:
                    candidates = filtered

            return candidates[:per_page]

        except Exception as e:
            import logging
            logging.warning(f'Life of Vids 搜索失败: {query}, {e}')
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

    def _parse_video_list(self, html: str, query: str) -> List[Dict]:
        """解析视频列表页面。"""
        candidates = []

        # Life of Vids 的视频通常在文章或视频卡片中
        # 匹配视频链接和缩略图
        video_pattern = r'<a[^>]*href="([^"]*(?:video|watch)[^"]*)"[^>]*>.*?<img[^>]*src="([^"]+)"'
        matches = re.findall(video_pattern, html, re.DOTALL | re.IGNORECASE)

        for idx, (video_path, thumbnail) in enumerate(matches[:12]):
            try:
                # 构建完整URL
                if video_path.startswith('http'):
                    video_url = video_path
                else:
                    video_url = f'{self.base_url}{video_path}' if video_path.startswith('/') else f'{self.base_url}/{video_path}'

                # 提取视频ID
                video_id = video_path.strip('/').split('/')[-1].split('?')[0]
                if not video_id:
                    video_id = f'vid_{idx}'

                # 处理缩略图URL
                if not thumbnail.startswith('http'):
                    thumbnail = f'{self.base_url}{thumbnail}' if thumbnail.startswith('/') else f'{self.base_url}/{thumbnail}'

                candidate = {
                    'candidate_id': f'lifeofvids_{video_id}',
                    'provider': self.provider_id,
                    'source_id': video_id,
                    'source_url': video_url,
                    'author': 'Life of Vids',
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

            # 查找视频源链接
            # 方案1: video 标签中的 source
            video_source_pattern = r'<source[^>]*src="([^"]+\.mp4[^"]*)"'
            match = re.search(video_source_pattern, html)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            # 方案2: 直接的 .mp4 链接
            mp4_pattern = r'href="([^"]+\.mp4[^"]*)"'
            match = re.search(mp4_pattern, html)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            # 方案3: data-src 属性
            data_src_pattern = r'data-src="([^"]+\.mp4[^"]*)"'
            match = re.search(data_src_pattern, html)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            return ''
        except Exception:
            return ''
