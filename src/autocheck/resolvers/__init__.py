"""Resolvers package."""
from autocheck.resolvers.arxiv import ArxivResolver
from autocheck.resolvers.crossref import CrossRefResolver
from autocheck.resolvers.openalex import OpenAlexResolver
from autocheck.resolvers.scihub import SciHubResolver
from autocheck.resolvers.title_downloader import TitleDownloader

__all__ = [
    "ArxivResolver",
    "CrossRefResolver",
    "OpenAlexResolver",
    "SciHubResolver",
    "TitleDownloader",
]
