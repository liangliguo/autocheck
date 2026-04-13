"""Unit tests for TitleDownloader (mocked, no network)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from autocheck.repository.library import PaperLibrary
from autocheck.resolvers.scihub import SciHubResolver
from autocheck.schemas.models import ReferenceEntry, ResolverMatch
from autocheck.services.reference_manager import ReferenceManager
from autocheck.resolvers.title_downloader import (
    TitleDownloader,
    curl_get,
    extract_scihub_pdf_url,
    download_from_scihub,
)


class TestCurlGet:
    """Tests for curl_get function."""

    def test_curl_get_returns_status_and_content(self, monkeypatch):
        """Test curl_get returns status code and content."""
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.stdout = b"Hello World\n200"
            result.returncode = 0
            return result

        monkeypatch.setattr(subprocess, "run", mock_run)
        status, content = curl_get("https://example.com")

        assert status == 200
        assert content == b"Hello World"

    def test_curl_get_handles_timeout(self, monkeypatch):
        """Test curl_get handles timeout gracefully."""
        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="curl", timeout=60)

        monkeypatch.setattr(subprocess, "run", mock_run)
        status, content = curl_get("https://example.com")

        assert status == 0
        assert content == b""


class TestExtractScihubPdfUrl:
    """Tests for extract_scihub_pdf_url function."""

    def test_extracts_from_embed_tag(self):
        """Test extraction from embed tag."""
        html = b'''
        <html>
            <embed type="application/pdf" src="//moscow.sci-hub.ru/123/paper.pdf#view=FitH">
        </html>
        '''
        url = extract_scihub_pdf_url(html, "https://sci-hub.se")
        assert url == "https://moscow.sci-hub.ru/123/paper.pdf"

    def test_extracts_from_iframe_pdf(self):
        """Test extraction from iframe with id='pdf'."""
        html = b'''
        <html>
            <iframe id="pdf" src="/downloads/paper.pdf"></iframe>
        </html>
        '''
        url = extract_scihub_pdf_url(html, "https://sci-hub.se")
        assert url == "https://sci-hub.se/downloads/paper.pdf"

    def test_returns_none_for_no_pdf(self):
        """Test returns None when no PDF link found."""
        html = b'<html><body>No PDF here</body></html>'
        url = extract_scihub_pdf_url(html, "https://sci-hub.se")
        assert url is None

    def test_extracts_from_button_without_pdf_suffix(self):
        """Sci-Hub mirrors sometimes use download paths without a .pdf suffix."""
        html = b"""
        <html>
            <button onclick="location.href='\\/downloads\\/2024-01-01\\/paper'">save</button>
        </html>
        """
        url = extract_scihub_pdf_url(html, "https://sci-hub.se")
        assert url == "https://sci-hub.se/downloads/2024-01-01/paper"

    def test_prefers_pdf_frame_even_without_pdf_like_path(self):
        """The Zotero resolver pattern relies on #pdf src directly."""
        html = b"""
        <html>
            <iframe id="pdf" src="/content/abcdef123456"></iframe>
        </html>
        """
        url = extract_scihub_pdf_url(html, "https://sci-hub.se")
        assert url == "https://sci-hub.se/content/abcdef123456"


class TestDownloadFromScihub:
    """Tests for download_from_scihub function."""

    def test_downloads_pdf_successfully(self, monkeypatch):
        """Test successful PDF download from Sci-Hub."""
        call_count = 0

        def mock_curl_get(url, timeout=60, referer=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                html = b'<embed type="application/pdf" src="//cdn.sci-hub.ru/paper.pdf">'
                return 200, html
            else:
                return 200, b"%PDF-1.4 fake pdf content"

        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
            mock_curl_get,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.scihub_common.curl_get",
            mock_curl_get,
        )

        pdf_bytes = download_from_scihub("10.1234/test", mirrors=["https://sci-hub.se"])

        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")

    def test_returns_none_when_all_mirrors_fail(self, monkeypatch):
        """Test returns None when all mirrors fail."""
        def mock_curl_get(url, timeout=60):
            return 500, b""

        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
            mock_curl_get,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.scihub_common.curl_get",
            mock_curl_get,
        )

        pdf_bytes = download_from_scihub("10.1234/test", mirrors=["https://sci-hub.se"])
        assert pdf_bytes is None

    def test_retries_next_mirror_when_first_pdf_is_invalid(self, monkeypatch):
        """A mirror may return an HTML challenge instead of a PDF; the downloader should continue."""
        calls = []

        def mock_curl_get(url, timeout=60, referer=None):
            calls.append((url, referer))
            if "sci-hub.se/10.1234/test" in url:
                return 200, b'<iframe id="pdf" src="/downloads/blocked"></iframe>'
            if url.endswith("/downloads/blocked"):
                return 200, b"<html>challenge</html>"
            if "sci-hub.st/10.1234/test" in url:
                return 200, b'<embed type="application/pdf" src="//cdn.sci-hub.st/paper.pdf">'
            if url == "https://cdn.sci-hub.st/paper.pdf":
                return 200, b"%PDF-1.4 valid pdf"
            return 404, b""

        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
            mock_curl_get,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.scihub_common.curl_get",
            mock_curl_get,
        )

        pdf_bytes = download_from_scihub(
            "https://doi.org/10.1234/test",
            mirrors=["https://sci-hub.se", "https://sci-hub.st"],
        )

        assert pdf_bytes == b"%PDF-1.4 valid pdf"
        assert ("https://cdn.sci-hub.st/paper.pdf", "https://sci-hub.st/10.1234/test") in calls

    def test_skips_known_unavailable_page_and_tries_next_mirror(self, monkeypatch):
        def mock_curl_get(url, timeout=60, referer=None):
            if url == "https://sci-hub.se/10.1234/test":
                return 200, b"<html>Unfortunately, Sci-Hub doesn't have the requested document</html>"
            if url == "https://sci-hub.st/10.1234/test":
                return 200, b'<iframe id="pdf" src="/content/abcdef123456"></iframe>'
            if url == "https://sci-hub.st/content/abcdef123456":
                return 200, b"%PDF-1.4 valid pdf"
            return 404, b""

        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
            mock_curl_get,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.scihub_common.curl_get",
            mock_curl_get,
        )

        pdf_bytes = download_from_scihub(
            "10.1234/test",
            mirrors=["https://sci-hub.se", "https://sci-hub.st"],
        )

        assert pdf_bytes == b"%PDF-1.4 valid pdf"

    def test_tries_encoded_doi_variant(self, monkeypatch):
        calls = []

        def mock_curl_get(url, timeout=60, referer=None):
            calls.append(url)
            if url == "https://sci-hub.se/10.1234%2Ftest":
                return 200, b'<iframe id="pdf" src="/downloads/paper.pdf"></iframe>'
            if url == "https://sci-hub.se/downloads/paper.pdf":
                return 200, b"%PDF-1.4 valid pdf"
            return 404, b""

        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
            mock_curl_get,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.scihub_common.curl_get",
            mock_curl_get,
        )

        pdf_bytes = download_from_scihub(
            "10.1234/test",
            mirrors=["https://sci-hub.se"],
        )

        assert pdf_bytes == b"%PDF-1.4 valid pdf"
        assert "https://sci-hub.se/10.1234%2Ftest" in calls


class TestTitleDownloader:
    """Tests for TitleDownloader class."""

    def test_download_by_title_tries_arxiv_first(self, monkeypatch):
        """Test that arXiv is tried before Sci-Hub."""
        arxiv_called = False

        def mock_arxiv_locate(self, ref):
            nonlocal arxiv_called
            arxiv_called = True
            return ResolverMatch(
                resolver_name="arxiv",
                title="Test Paper",
                authors=["Author One"],
                year=2023,
                pdf_url="https://arxiv.org/pdf/2301.00001.pdf",
                score=0.9,
            )

        def mock_curl_get(url, timeout=60):
            return 200, b"%PDF-1.4 arxiv pdf"

        monkeypatch.setattr(
            "autocheck.resolvers.arxiv.ArxivResolver.locate",
            mock_arxiv_locate,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
            mock_curl_get,
        )

        downloader = TitleDownloader()
        pdf_bytes, match = downloader.download_by_title("Test Paper")

        assert arxiv_called is True
        assert pdf_bytes is not None
        assert match.resolver_name == "arxiv"

    def test_download_by_title_falls_back_to_scihub(self, monkeypatch):
        """Test fallback to Sci-Hub when arXiv fails."""
        def mock_arxiv_locate(self, ref):
            return None

        def mock_crossref_locate(self, ref):
            return ResolverMatch(
                resolver_name="crossref",
                title="Test Paper",
                authors=[],
                year=2023,
                external_id="doi:10.1234/test",
                score=0.8,
            )

        def mock_download_from_scihub(doi, mirrors=None):
            return b"%PDF-1.4 scihub pdf"

        monkeypatch.setattr(
            "autocheck.resolvers.arxiv.ArxivResolver.locate",
            mock_arxiv_locate,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.crossref.CrossRefResolver.locate",
            mock_crossref_locate,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.download_from_scihub",
            mock_download_from_scihub,
        )

        downloader = TitleDownloader()
        pdf_bytes, match = downloader.download_by_title("Some Paper Title")

        assert pdf_bytes is not None
        assert match.resolver_name == "scihub"

    def test_download_by_title_returns_none_when_all_fail(self, monkeypatch):
        """Test returns None when both arXiv and Sci-Hub fail."""
        def mock_arxiv_locate(self, ref):
            return None

        def mock_crossref_locate(self, ref):
            return None

        monkeypatch.setattr(
            "autocheck.resolvers.arxiv.ArxivResolver.locate",
            mock_arxiv_locate,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.crossref.CrossRefResolver.locate",
            mock_crossref_locate,
        )

        downloader = TitleDownloader()
        pdf_bytes, match = downloader.download_by_title("Nonexistent Paper")

        assert pdf_bytes is None
        assert match is None

    def test_download_by_title_saves_to_output_path(self, monkeypatch, tmp_path):
        """Test that PDF is saved to output_path when provided."""
        def mock_arxiv_locate(self, ref):
            return ResolverMatch(
                resolver_name="arxiv",
                title="Test Paper",
                pdf_url="https://arxiv.org/pdf/test.pdf",
                score=0.9,
            )

        def mock_curl_get(url, timeout=60, referer=None):
            return 200, b"%PDF-1.4 test content"

        monkeypatch.setattr(
            "autocheck.resolvers.arxiv.ArxivResolver.locate",
            mock_arxiv_locate,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
            mock_curl_get,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.scihub_common.curl_get",
            mock_curl_get,
        )

        output_file = tmp_path / "paper.pdf"
        downloader = TitleDownloader()
        pdf_bytes, match = downloader.download_by_title("Test Paper", output_path=output_file)

        assert pdf_bytes is not None
        assert output_file.exists()
        assert output_file.read_bytes() == b"%PDF-1.4 test content"

    def test_initialization(self):
        """Test TitleDownloader initializes correctly."""
        downloader = TitleDownloader()
        assert downloader.arxiv_resolver is not None
        assert downloader.crossref_resolver is not None
        assert len(downloader.scihub_mirrors) > 0

    def test_custom_mirrors(self):
        """Test TitleDownloader accepts custom mirrors."""
        custom_mirrors = ["https://custom.mirror.com"]
        downloader = TitleDownloader(scihub_mirrors=custom_mirrors)
        assert downloader.scihub_mirrors == custom_mirrors


class TestSciHubResolver:
    def test_locate_extracts_pdf_url_without_pdf_suffix(self, monkeypatch):
        def mock_curl_get(url, timeout=60, referer=None):
            return 200, b'<iframe id="pdf" src="/downloads/2024-01-01/paper"></iframe>'

        monkeypatch.setattr(
            "autocheck.resolvers.scihub.curl_get",
            mock_curl_get,
        )

        resolver = SciHubResolver()
        match = resolver.locate(
            ReferenceEntry(
                ref_id="[1]",
                raw_text="[1] ref",
                title="Paper",
                doi="doi:10.1234/test",
            )
        )

        assert match is not None
        assert match.pdf_url == "https://sci-hub.se/downloads/2024-01-01/paper"
        assert match.external_id == "doi:10.1234/test"

    def test_locate_skips_unavailable_page(self, monkeypatch):
        def mock_curl_get(url, timeout=60, referer=None):
            if url == "https://sci-hub.se/10.1234/test":
                return 200, b"<html>article not found</html>"
            if url == "https://sci-hub.st/10.1234/test":
                return 200, b'<iframe id="pdf" src="/content/abcdef123456"></iframe>'
            return 404, b""

        monkeypatch.setattr(
            "autocheck.resolvers.scihub.curl_get",
            mock_curl_get,
        )

        resolver = SciHubResolver(custom_url="https://sci-hub.se")
        resolver.mirrors = ["https://sci-hub.se", "https://sci-hub.st"]
        match = resolver.locate(
            ReferenceEntry(
                ref_id="[1]",
                raw_text="[1] ref",
                title="Paper",
                doi="10.1234/test",
            )
        )

        assert match is not None
        assert match.pdf_url == "https://sci-hub.st/content/abcdef123456"


class TestReferenceManagerSciHubDownload:
    def test_download_pdf_uses_curl_for_scihub_with_referer(self, monkeypatch, tmp_path):
        calls = []

        def mock_download_pdf_bytes(url, timeout=120, referer=None):
            calls.append((url, timeout, referer))
            return b"%PDF-1.4 scihub"

        monkeypatch.setattr(
            "autocheck.services.reference_manager.download_pdf_bytes",
            mock_download_pdf_bytes,
        )

        library = PaperLibrary(tmp_path / "downloads", tmp_path / "processed")
        manager = ReferenceManager(library)
        match = ResolverMatch(
            resolver_name="scihub",
            title="Paper",
            pdf_url="https://cdn.sci-hub.se/download",
            landing_page_url="https://sci-hub.se/10.1234/test",
            external_id="doi:10.1234/test",
            score=1.0,
        )

        pdf_bytes = manager._download_pdf(match)

        assert pdf_bytes == b"%PDF-1.4 scihub"
        assert calls == [("https://cdn.sci-hub.se/download", 120, "https://sci-hub.se/10.1234/test")]

    def test_download_pdf_rejects_non_pdf_for_non_scihub(self, monkeypatch, tmp_path):
        class MockResponse:
            content = b"<html>no pdf</html>"

            def raise_for_status(self):
                return None

        monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: MockResponse())

        library = PaperLibrary(tmp_path / "downloads", tmp_path / "processed")
        manager = ReferenceManager(library)
        match = ResolverMatch(
            resolver_name="arxiv",
            title="Paper",
            pdf_url="https://example.com/paper.pdf",
            score=1.0,
        )

        with pytest.raises(ValueError, match="not a PDF"):
            manager._download_pdf(match)
