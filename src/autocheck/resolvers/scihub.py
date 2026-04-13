from __future__ import annotations

from typing import Optional

from autocheck.resolvers.scihub_common import (
    build_scihub_mirror_list,
    curl_get,
    extract_scihub_pdf_url,
    iter_doi_candidates,
    page_indicates_unavailable,
)
from autocheck.schemas.models import ReferenceEntry, ResolverMatch


class SciHubResolver:
    """
    Resolver that downloads PDFs from Sci-Hub using DOI.
    
    Note: Sci-Hub mirrors change frequently. This resolver tries multiple known mirrors.
    Supports custom mirror URL via configuration.
    """
    
    name = "scihub"
    
    def __init__(self, custom_url: str = ""):
        """
        Initialize SciHubResolver with optional custom mirror URL.
        
        Args:
            custom_url: Custom Sci-Hub mirror URL. If provided, it will be tried first.
        """
        self.custom_url = custom_url.strip() if custom_url else ""
        self.mirrors = build_scihub_mirror_list(self.custom_url)
    
    def locate(self, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        """Locate a paper on Sci-Hub by DOI."""
        if not reference.doi:
            return None
        
        doi_candidates = iter_doi_candidates(reference.doi)
        if not doi_candidates:
            return None
        
        canonical_doi = doi_candidates[0]
        for mirror in self.mirrors:
            for doi_candidate in doi_candidates:
                pdf_url = self._try_mirror(mirror, doi_candidate)
                if pdf_url:
                    return ResolverMatch(
                        resolver_name=self.name,
                        title=reference.title,
                        authors=reference.authors or [],
                        year=reference.year,
                        pdf_url=pdf_url,
                        landing_page_url=f"{mirror}/{doi_candidate}",
                        external_id=f"doi:{canonical_doi}",
                        score=1.0,  # DOI is exact match
                    )
        
        return None
    
    def _try_mirror(self, mirror: str, doi: str) -> Optional[str]:
        """Try to get PDF URL from a specific Sci-Hub mirror."""
        try:
            status_code, content = curl_get(f"{mirror}/{doi}")
            if status_code != 200 or not content or page_indicates_unavailable(content):
                return None

            return extract_scihub_pdf_url(content, mirror)
        except Exception:
            return None
