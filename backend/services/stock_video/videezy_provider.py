# -*- coding: utf-8 -*-
"""Videezy 免费视频素材 Provider。"""

import re
from typing import Dict, List
from urllib.parse import urlencode

from .base_provider import StockVideoProvider


class VideezyProvider(StockVideoProvider):
    """基于 Videezy 网站搜索免费视频素材，无需 API Key。

    Videezy 提供免费和付费视频素材，免费素材大多需要注明出处。
    网站: https://www.videezy.com/
    许可: 主要是 CC BY 3.0，部分 CC0
    """

    provider_id = 'videezy'
    display_name = 'Videezy'
    license_name = 'Videezy License (多为 CC BY 3.0)'
    license_url = 'https://www.videezy.com/terms'
    requires_api_key = False
    search_url = 'https://www.videezy.com/free-video/'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        """搜索 Videezy 免费视频素材。

        注意：Videezy 没有公开 API，此实现通过解析 HTML 获取视频信息。
        """
        try:
            # 构建搜索URL - Videezy使用路径式搜索
            # 例如: https://www.videezy.com/free-video/nature
            search_query = query.lower().replace(' ', '-')
            url = f'{self.search_url}{search_query}'

            # 获取搜索结果页面
            html = self._get_html(url)
            if not html:
                return []

            # 解析视频列表
            candidates = self._parse_search_results(html, query)
            return candidates[:per_page]

        except Exception as e:
            import logging
            logging.warning(f'Videezy 搜索失败: {query}, {e}')
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

        # Videezy 的视频卡片通常包含视频链接和缩略图
        # 匹配模式: <a href="/free-video/...">
        video_pattern = r'<a[^>]*href="(/free-video/[^"]+)"[^>]*>.*?<img[^>]*src="([^"]+)"'
        matches = re.findall(video_pattern, html, re.DOTALL)

        for idx, (video_path, thumbnail) in enumerate(matches[:12]):
            try:
                # 构建完整URL
                video_url = f'https://www.videezy.com{video_path}'

                # 提取视频ID和标题
                path_parts = video_path.split('/')
                video_id = path_parts[-1] if len(path_parts) > 0 else f'vid_{idx}'

                candidate = {
                    'candidate_id': f'videezy_{video_id}',
                    'provider': self.provider_id,
                    'source_id': video_id,
                    'source_url': video_url,
                    'author': 'Videezy Community',
                    'license': 'Creative Commons BY 3.0',
                    'license_url': 'https://creativecommons.org/licenses/by/3.0/',
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

            # 查找免费下载链接
            # Videezy 的下载按钮通常有 data-download 或类似属性
            download_pattern = r'href="(https://[^"]*videezy[^"]*\.mp4[^"]*)"'
            match = re.search(download_pattern, html)
            if match:
                return match.group(1)

            # 备用方案：查找 CDN 链接
            cdn_pattern = r'"(https://cdn\.videezy\.com/[^"]+\.mp4)"'
            match = re.search(cdn_pattern, html)
            if match:
                return match.group(1)

            return ''
        except Exception:
            return ''
