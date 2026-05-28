# -*- coding: utf-8 -*-
"""Videvo 免费视频素材 Provider。"""

import re
from typing import Dict, List
from urllib.parse import urlencode, quote

from .base_provider import StockVideoProvider


class VidevoProvider(StockVideoProvider):
    """基于 Videvo 网站搜索免费视频素材，无需 API Key。

    Videvo 提供免费和付费视频素材，免费素材需要注明出处。
    网站: https://www.videvo.net/
    许可: 部分 CC0，部分 Videvo Attribution License
    """

    provider_id = 'videvo'
    display_name = 'Videvo'
    license_name = 'Videvo License (需查看具体视频许可)'
    license_url = 'https://www.videvo.net/terms/'
    requires_api_key = False
    search_url = 'https://www.videvo.net/search/'

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        """搜索 Videvo 免费视频素材。

        注意：Videvo 没有公开 API，此实现通过解析 HTML 获取视频信息。
        由于网站结构可能变化，此方法可能需要定期维护。
        """
        try:
            # 构建搜索URL
            search_params = {
                'q': query,
                'content-type': 'stock-video-footage',
                'license': 'free'  # 只搜索免费素材
            }
            url = f'{self.search_url}?{urlencode(search_params)}'

            # 获取搜索结果页面
            html = self._get_html(url)
            if not html:
                return []

            # 解析视频列表
            candidates = self._parse_search_results(html, query)
            return candidates[:per_page]

        except Exception as e:
            import logging
            logging.warning(f'Videvo 搜索失败: {query}, {e}')
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
        """解析搜索结果页面，提取视频信息。

        注意：此方法依赖 Videvo 网站的 HTML 结构，可能需要根据网站更新调整。
        """
        candidates = []

        # 使用正则表达式提取视频卡片信息
        # Videvo 的视频通常在 class="video-item" 或类似的容器中
        video_pattern = r'<a[^>]*href="(/video/[^"]+)"[^>]*>.*?<img[^>]*src="([^"]+)".*?</a>'
        matches = re.findall(video_pattern, html, re.DOTALL)

        for idx, (video_path, thumbnail) in enumerate(matches[:12]):
            try:
                # 构建完整URL
                video_url = f'https://www.videvo.net{video_path}'

                # 提取视频ID
                video_id = video_path.split('/')[-1].split('-')[0] if '/' in video_path else f'vid_{idx}'

                # 获取视频详情页（可选，用于获取更多信息）
                # 为了性能，这里只返回基本信息
                candidate = {
                    'candidate_id': f'videvo_{video_id}',
                    'provider': self.provider_id,
                    'source_id': video_id,
                    'source_url': video_url,
                    'author': 'Videvo',
                    'license': self.license_name,
                    'license_url': self.license_url,
                    'download_url': video_url,  # 实际下载需要访问详情页
                    'width': 1920,  # 默认值
                    'height': 1080,
                    'duration': 0,
                    'fps': 0,
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
            # Videvo 的免费下载链接通常在 data-download-url 或类似属性中
            download_pattern = r'data-download-url="([^"]+)"'
            match = re.search(download_pattern, html)
            if match:
                return match.group(1)

            # 备用方案：查找直接的 .mp4 链接
            mp4_pattern = r'href="(https://[^"]+\.mp4[^"]*)"'
            match = re.search(mp4_pattern, html)
            if match:
                return match.group(1)

            return ''
        except Exception:
            return ''
