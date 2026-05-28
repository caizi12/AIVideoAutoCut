# -*- coding: utf-8 -*-
"""公开视频素材 Provider。"""

from .internet_archive_provider import InternetArchiveProvider
from .nasa_provider import NasaVideoProvider
from .pexels_provider import PexelsProvider
from .pixabay_provider import PixabayProvider
from .wikimedia_provider import WikimediaCommonsProvider
from .videvo_provider import VidevoProvider
from .videezy_provider import VideezyProvider
from .mazwai_provider import MazwaiProvider
from .lifeofvids_provider import LifeOfVidsProvider
from .splitshire_provider import SplitshireProvider
from .coverr_provider import CoverrProvider

__all__ = [
    'InternetArchiveProvider',
    'NasaVideoProvider',
    'PexelsProvider',
    'PixabayProvider',
    'WikimediaCommonsProvider',
    'VidevoProvider',
    'VideezyProvider',
    'MazwaiProvider',
    'LifeOfVidsProvider',
    'SplitshireProvider',
    'CoverrProvider'
]
