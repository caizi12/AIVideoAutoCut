# -*- coding: utf-8 -*-
"""公开视频素材 Provider 抽象。"""

import json
import logging
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """素材 Provider 调用失败。"""


class StockVideoProvider:
    """公开视频素材搜索 Provider 基类。"""

    provider_id = ''
    display_name = ''
    license_name = ''
    license_url = ''
    requires_api_key = True

    def __init__(self, api_key: str = '', timeout: int = 20):
        self.api_key = (api_key or '').strip()
        self.timeout = max(3, int(timeout or 20))

    @property
    def available(self) -> bool:
        """是否具备调用远程 API 的必要配置。"""
        if not self.requires_api_key:
            return True
        return bool(self.api_key)

    def status(self) -> Dict:
        """返回前端可展示的配置状态，不能暴露完整密钥。"""
        return {
            'provider': self.provider_id,
            'name': self.display_name,
            'available': self.available,
            'missing': [] if self.available else ['api_key'],
            'requires_api_key': self.requires_api_key,
            'license': self.license_name,
            'license_url': self.license_url
        }

    def search(self, query: str, orientation: str = 'landscape', per_page: int = 6) -> List[Dict]:
        """搜索素材候选。"""
        raise NotImplementedError

    def _get_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict:
        request = Request(url, headers=headers or {})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or 'utf-8'
                raw = response.read().decode(charset, errors='replace')
                return json.loads(raw or '{}')
        except HTTPError as e:
            detail = ''
            try:
                detail = e.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                detail = str(e)
            logger.warning(f'{self.display_name} API 返回异常: HTTP {e.code}, {detail}')
            raise ProviderError(f'{self.display_name} 搜索失败（HTTP {e.code}）')
        except URLError as e:
            logger.warning(f'{self.display_name} API 网络异常: {e}')
            raise ProviderError(f'{self.display_name} 网络请求失败，请检查网络或代理配置')
        except json.JSONDecodeError:
            logger.warning(f'{self.display_name} API 返回非 JSON 内容')
            raise ProviderError(f'{self.display_name} 返回数据格式异常')

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(float(value))
        except Exception:
            return default
