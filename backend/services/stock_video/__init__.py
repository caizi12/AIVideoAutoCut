# -*- coding: utf-8 -*-
"""公开视频素材 Provider。"""

from .internet_archive_provider import InternetArchiveProvider
from .nasa_provider import NasaVideoProvider
from .pexels_provider import PexelsProvider
from .pixabay_provider import PixabayProvider
from .wikimedia_provider import WikimediaCommonsProvider

__all__ = [
    'InternetArchiveProvider',
    'NasaVideoProvider',
    'PexelsProvider',
    'PixabayProvider',
    'WikimediaCommonsProvider'
]
