"""Unit tests for TitleDownloader (mocked, no network)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autocheck.schemas.models import ReferenceEntry, ResolverMatch
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


class TestDownloadFromScihub:
    """Tests for download_from_scihub function."""

    def test_downloads_pdf_successfully(self, monkeypatch):
        """Test successful PDF download from Sci-Hub."""
        call_count = 0

        def mock_curl_get(url, timeout=60):
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

        pdf_bytes = download_from_scihub("10.1234/test", mirrors=["https://sci-hub.se"])
        assert pdf_bytes is None


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

        def mock_curl_get(url, timeout=60):
            return 200, b"%PDF-1.4 test content"

        monkeypatch.setattr(
            "autocheck.resolvers.arxiv.ArxivResolver.locate",
            mock_arxiv_locate,
        )
        monkeypatch.setattr(
            "autocheck.resolvers.title_downloader.curl_get",
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
