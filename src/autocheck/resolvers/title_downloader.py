"""
Title-based paper downloader.

Downloads papers by title using a fallback strategy:
1. Search arXiv and download if found
2. Search CrossRef for DOI, then download from Sci-Hub

Adapted from https://github.com/liangliguo/scihub
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from autocheck.schemas.models import ReferenceEntry, ResolverMatch
from autocheck.resolvers.arxiv import ArxivResolver
from autocheck.resolvers.crossref import CrossRefResolver
from autocheck.resolvers.scihub_common import (
    SCIHUB_MIRRORS,
    build_scihub_mirror_list,
    curl_get,
    download_pdf_bytes,
    extract_scihub_pdf_url,
    normalize_doi,
)


def download_from_scihub(doi: str, mirrors: list[str] | None = None) -> Optional[bytes]:
    """Download PDF from Sci-Hub using DOI."""
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return None

    for mirror in build_scihub_mirror_list(mirrors=mirrors):
        try:
            url = f"{mirror}/{normalized_doi}"
            status, content = curl_get(url)
            if status != 200 or not content:
                continue

            pdf_url = extract_scihub_pdf_url(content, mirror)
            if not pdf_url:
                continue

            pdf_content = download_pdf_bytes(pdf_url, timeout=120, referer=url)
            if not pdf_content:
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
        self.scihub_mirrors = build_scihub_mirror_list(scihub_url, scihub_mirrors)

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
        return download_pdf_bytes(url, timeout=120)
