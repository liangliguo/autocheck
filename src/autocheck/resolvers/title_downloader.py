"""
Title-based paper downloader.

Downloads papers by title using a fallback strategy:
1. Search arXiv and download if found
2. Search CrossRef for DOI, then download from Sci-Hub

Adapted from https://github.com/liangliguo/scihub
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from autocheck.schemas.models import ReferenceEntry, ResolverMatch
from autocheck.resolvers.arxiv import ArxivResolver
from autocheck.resolvers.crossref import CrossRefResolver


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SCIHUB_MIRRORS = [
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
    "https://sci-hub.ren",
]


def curl_get(url: str, timeout: int = 60) -> tuple[int, bytes]:
    """Use curl to fetch URL content (bypasses some anti-bot measures)."""
    try:
        result = subprocess.run(
            [
                "curl", "-sL",
                "-A", USER_AGENT,
                "--connect-timeout", str(timeout),
                "-w", "\n%{http_code}",
                url
            ],
            capture_output=True,
            timeout=timeout + 10,
            check=False,
        )
        output = result.stdout
        lines = output.rsplit(b"\n", 1)
        if len(lines) == 2:
            content, code_bytes = lines
            try:
                status_code = int(code_bytes)
            except ValueError:
                status_code = 0
                content = output
        else:
            content = output
            status_code = 200 if result.returncode == 0 else 0
        return status_code, content
    except subprocess.TimeoutExpired:
        return 0, b""
    except Exception:
        return 0, b""


def extract_scihub_pdf_url(html: bytes, mirror: str) -> Optional[str]:
    """Extract PDF URL from Sci-Hub page HTML."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return None

    pdf_url = None

    # Method 1: embed tag with type="application/pdf"
    embed = soup.find("embed", {"type": "application/pdf"})
    if embed and embed.get("src"):
        pdf_url = embed["src"]
        if "#" in pdf_url:
            pdf_url = pdf_url.split("#")[0]

    # Method 2: iframe#pdf
    if not pdf_url:
        iframe = soup.find("iframe", {"id": "pdf"})
        if iframe and iframe.get("src"):
            pdf_url = iframe["src"]

    # Method 3: button with onclick containing location.href
    if not pdf_url:
        button = soup.find("button", onclick=True)
        if button:
            onclick = button.get("onclick", "").replace("\\/", "/")
            match = re.search(r"location.href='([^']+)'", onclick)
            if match:
                pdf_url = match.group(1)

    # Method 4: any iframe with src
    if not pdf_url:
        iframe = soup.find("iframe")
        if iframe and iframe.get("src"):
            pdf_url = iframe["src"]

    if not pdf_url:
        return None

    # Normalize URL
    if pdf_url.startswith("//"):
        pdf_url = "https:" + pdf_url
    elif pdf_url.startswith("/"):
        pdf_url = mirror + pdf_url

    return pdf_url


def download_from_scihub(doi: str, mirrors: list[str] | None = None) -> Optional[bytes]:
    """Download PDF from Sci-Hub using DOI."""
    if mirrors is None:
        mirrors = SCIHUB_MIRRORS

    for mirror in mirrors:
        try:
            url = f"{mirror}/{doi}"
            status, content = curl_get(url)
            if status != 200 or not content:
                continue

            pdf_url = extract_scihub_pdf_url(content, mirror)
            if not pdf_url:
                continue

            # Download the PDF
            pdf_status, pdf_content = curl_get(pdf_url, timeout=120)
            if pdf_status != 200 or not pdf_content:
                continue

            # Verify it's a PDF
            if not pdf_content.startswith(b"%PDF"):
                continue

            return pdf_content

        except Exception:
            continue

    return None


class TitleDownloader:
    """
    Downloads papers by title using a fallback strategy:
    1. Search arXiv and download if found
    2. Search CrossRef for DOI, then download from Sci-Hub
    """

    def __init__(self, scihub_url: str = "", scihub_mirrors: list[str] | None = None) -> None:
        self.arxiv_resolver = ArxivResolver()
        self.crossref_resolver = CrossRefResolver()
        # Support both custom URL and mirror list
        if scihub_url:
            # Custom URL takes priority
            self.scihub_mirrors = [scihub_url] + [m for m in SCIHUB_MIRRORS if m != scihub_url]
        elif scihub_mirrors:
            self.scihub_mirrors = scihub_mirrors
        else:
            self.scihub_mirrors = SCIHUB_MIRRORS

    def download_by_title(
        self,
        title: str,
        output_path: Path | None = None,
    ) -> tuple[Optional[bytes], Optional[ResolverMatch]]:
        """
        Download a paper by title.

        Args:
            title: The paper title to search for
            output_path: Optional path to save the PDF

        Returns:
            Tuple of (pdf_bytes, match) if successful, (None, None) if failed
        """
        reference = ReferenceEntry(
            ref_id="title_search",
            raw_text=title,
            title=title,
        )

        # Strategy 1: Try arXiv first
        pdf_bytes, match = self._try_arxiv(reference)
        if pdf_bytes and match:
            if output_path:
                output_path.write_bytes(pdf_bytes)
            return pdf_bytes, match

        # Strategy 2: Try CrossRef + Sci-Hub
        pdf_bytes, match = self._try_crossref_scihub(reference)
        if pdf_bytes and match:
            if output_path:
                output_path.write_bytes(pdf_bytes)
            return pdf_bytes, match

        return None, None

    def download_reference(
        self,
        reference: ReferenceEntry,
        output_path: Path | None = None,
    ) -> tuple[Optional[bytes], Optional[ResolverMatch]]:
        """
        Download a paper using ReferenceEntry metadata.

        Tries in order:
        1. arXiv (if arxiv_id is present, or by title search)
        2. Sci-Hub (if DOI is present, or after CrossRef lookup)

        Args:
            reference: ReferenceEntry with paper metadata
            output_path: Optional path to save the PDF

        Returns:
            Tuple of (pdf_bytes, match) if successful, (None, None) if failed
        """
        # Strategy 1: Try arXiv
        pdf_bytes, match = self._try_arxiv(reference)
        if pdf_bytes and match:
            if output_path:
                output_path.write_bytes(pdf_bytes)
            return pdf_bytes, match

        # Strategy 2: Try Sci-Hub with existing DOI or CrossRef lookup
        pdf_bytes, match = self._try_crossref_scihub(reference)
        if pdf_bytes and match:
            if output_path:
                output_path.write_bytes(pdf_bytes)
            return pdf_bytes, match

        return None, None

    def _try_arxiv(
        self,
        reference: ReferenceEntry,
    ) -> tuple[Optional[bytes], Optional[ResolverMatch]]:
        """Try to find and download from arXiv."""
        try:
            match = self.arxiv_resolver.locate(reference)
            if not match or not match.pdf_url:
                return None, None

            # Download PDF from arXiv
            pdf_bytes = self._download_pdf(match.pdf_url)
            if pdf_bytes:
                return pdf_bytes, match
        except Exception:
            pass

        return None, None

    def _try_crossref_scihub(
        self,
        reference: ReferenceEntry,
    ) -> tuple[Optional[bytes], Optional[ResolverMatch]]:
        """Try CrossRef for DOI, then download from Sci-Hub."""
        doi = reference.doi

        # If no DOI, try CrossRef lookup
        if not doi:
            try:
                match = self.crossref_resolver.locate(reference)
                if match and match.external_id:
                    # Extract DOI from external_id (format: "doi:10.xxx/xxx")
                    if match.external_id.startswith("doi:"):
                        doi = match.external_id[4:]
                    else:
                        doi = match.external_id
            except Exception:
                pass

        if not doi:
            return None, None

        # Download from Sci-Hub
        pdf_bytes = download_from_scihub(doi, self.scihub_mirrors)
        if pdf_bytes:
            match = ResolverMatch(
                resolver_name="scihub",
                title=reference.title or "",
                authors=reference.authors or [],
                year=reference.year,
                pdf_url=None,
                landing_page_url=f"https://doi.org/{doi}",
                external_id=f"doi:{doi}",
                score=1.0,
            )
            return pdf_bytes, match

        return None, None

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF from URL using curl."""
        status, content = curl_get(url, timeout=120)
        if status == 200 and content and content.startswith(b"%PDF"):
            return content
        return None
