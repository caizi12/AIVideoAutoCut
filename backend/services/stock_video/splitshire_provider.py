# -*- coding: utf-8 -*-
"""Splitshire 免费视频素材 Provider。"""

import re
from typing import Dict, List

from .base_provider import StockVideoProvider


class SplitshireProvider(StockVideoProvider):
    """基于 Splitshire 网站搜索免费视频素材，无需 API Key。

    Splitshire 提供免费的图片和视频素材，可用于个人和商业目的。
    网站: https://www.splitshire.com/
    许可: 免费用于个人和商业用途，无需注明出处
    """

    provider_id = 'splitshire'
    display_name = 'Splitshire'
    license_name = 'Splitshire Free License'
    license_url = 'https://www.splitshire.com/licence/'
    requires_api_key = False
    base_url = 'https://www.splitshire.com'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        """搜索 Splitshire 免费视频素材。

        注意：Splitshire 没有公开搜索 API，此实现通过解析视频分类页面获取内容。
        """
        try:
            # Splitshire 的视频页面
            url = f'{self.base_url}/category/videos/'

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
                    searchable = f"{c.get('source_url', '')} {c.get('source_id', '')}".lower()
                    if any(word in searchable for word in query_lower.split()):
                        filtered.append(c)
                if filtered:
                    candidates = filtered

            return candidates[:per_page]

        except Exception as e:
            import logging
            logging.warning(f'Splitshire 搜索失败: {query}, {e}')
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

        # Splitshire 的视频文章链接
        # 匹配文章链接和缩略图
        article_pattern = r'<article[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>.*?<img[^>]*src="([^"]+)".*?</article>'
        matches = re.findall(article_pattern, html, re.DOTALL)

        for idx, (article_url, thumbnail) in enumerate(matches[:12]):
            try:
                # 确保是完整URL
                if not article_url.startswith('http'):
                    article_url = f'{self.base_url}{article_url}' if article_url.startswith('/') else f'{self.base_url}/{article_url}'

                # 提取视频ID
                video_id = article_url.strip('/').split('/')[-1].split('?')[0]
                if not video_id:
                    video_id = f'vid_{idx}'

                # 处理缩略图URL
                if not thumbnail.startswith('http'):
                    thumbnail = f'{self.base_url}{thumbnail}' if thumbnail.startswith('/') else thumbnail

                candidate = {
                    'candidate_id': f'splitshire_{video_id}',
                    'provider': self.provider_id,
                    'source_id': video_id,
                    'source_url': article_url,
                    'author': 'Splitshire',
                    'license': self.license_name,
                    'license_url': self.license_url,
                    'download_url': article_url,  # 需要访问详情页获取实际下载链接
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

            # 查找下载链接
            # 方案1: 下载按钮链接
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

            # 方案3: 直接的 .mp4 链接
            mp4_pattern = r'href="([^"]+\.mp4[^"]*)"'
            match = re.search(mp4_pattern, html)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            return ''
        except Exception:
            return ''
