# -*- coding: utf-8 -*-
"""Mazwai 精选免费视频素材 Provider。"""

import re
from typing import Dict, List

from .base_provider import StockVideoProvider


class MazwaiProvider(StockVideoProvider):
    """基于 Mazwai 网站搜索精选免费视频素材，无需 API Key。

    Mazwai 提供由专家精心挑选的高质量免费视频素材。
    网站: https://mazwai.com/
    许可: CC BY 3.0，需要注明原作者
    """

    provider_id = 'mazwai'
    display_name = 'Mazwai'
    license_name = 'Creative Commons BY 3.0'
    license_url = 'https://creativecommons.org/licenses/by/3.0/'
    requires_api_key = False
    base_url = 'https://mazwai.com'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        """搜索 Mazwai 精选视频素材。

        注意：Mazwai 没有公开搜索 API，此实现通过解析分类页面获取视频。
        """
        try:
            # Mazwai 主要通过分类浏览，我们尝试访问主页获取最新视频
            url = f'{self.base_url}/'

            html = self._get_html(url)
            if not html:
                return []

            # 解析视频列表
            candidates = self._parse_video_list(html, query)

            # 根据查询词过滤（简单的关键词匹配）
            if query:
                query_lower = query.lower()
                filtered = [c for c in candidates if query_lower in c.get('source_url', '').lower()]
                if filtered:
                    candidates = filtered

            return candidates[:per_page]

        except Exception as e:
            import logging
            logging.warning(f'Mazwai 搜索失败: {query}, {e}')
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

        # Mazwai 的视频链接通常是 /video/video-name/
        video_pattern = r'<a[^>]*href="(/video/[^"]+)"[^>]*>.*?<img[^>]*src="([^"]+)"'
        matches = re.findall(video_pattern, html, re.DOTALL)

        for idx, (video_path, thumbnail) in enumerate(matches[:12]):
            try:
                # 构建完整URL
                video_url = f'{self.base_url}{video_path}'

                # 提取视频ID
                video_id = video_path.strip('/').split('/')[-1]

                # 从路径提取标题（用作作者信息的一部分）
                title = video_id.replace('-', ' ').title()

                candidate = {
                    'candidate_id': f'mazwai_{video_id}',
                    'provider': self.provider_id,
                    'source_id': video_id,
                    'source_url': video_url,
                    'author': f'Mazwai - {title}',
                    'license': self.license_name,
                    'license_url': self.license_url,
                    'download_url': video_url,  # 需要访问详情页获取实际下载链接
                    'width': 1920,
                    'height': 1080,
                    'duration': 0,
                    'fps': 24,
                    'query': query,
                    'quality': 'hd',
                    'local_path': '',
                    'score': 0,
                    'thumbnail': thumbnail if thumbnail.startswith('http') else f'{self.base_url}{thumbnail}'
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

            # 查找下载链接 - Mazwai 通常有直接的 .mp4 链接
            # 查找 video 标签中的 source
            video_source_pattern = r'<source[^>]*src="([^"]+\.mp4[^"]*)"'
            match = re.search(video_source_pattern, html)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            # 备用方案：查找下载按钮
            download_pattern = r'href="([^"]+\.mp4[^"]*)"[^>]*download'
            match = re.search(download_pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                return url if url.startswith('http') else f'{self.base_url}{url}'

            return ''
        except Exception:
            return ''
