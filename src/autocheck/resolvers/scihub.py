from __future__ import annotations

import re
from typing import Optional

import requests

from autocheck.schemas.models import ReferenceEntry, ResolverMatch


class SciHubResolver:
    """
    Resolver that downloads PDFs from Sci-Hub using DOI.
    
    Note: Sci-Hub mirrors change frequently. This resolver tries multiple known mirrors.
    """
    
    name = "scihub"
    
    # Common Sci-Hub mirrors (may need updates as domains change)
    mirrors = [
        "https://sci-hub.se",
        "https://sci-hub.st",
        "https://sci-hub.ru",
        "https://sci-hub.ren",
    ]
    
    def locate(self, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        """Locate a paper on Sci-Hub by DOI."""
        if not reference.doi:
            return None
        
        doi = self._normalize_doi(reference.doi)
        if not doi:
            return None
        
        for mirror in self.mirrors:
            pdf_url = self._try_mirror(mirror, doi)
            if pdf_url:
                return ResolverMatch(
                    resolver_name=self.name,
                    title=reference.title,
                    authors=reference.authors or [],
                    year=reference.year,
                    pdf_url=pdf_url,
                    landing_page_url=f"{mirror}/{doi}",
                    external_id=f"doi:{doi}",
                    score=1.0,  # DOI is exact match
                )
        
        return None
    
    def _normalize_doi(self, doi: str) -> Optional[str]:
        """Extract clean DOI from various formats."""
        doi = doi.strip()
        
        # Remove common prefixes
        for prefix in ["https://doi.org/", "http://doi.org/", "doi:", "DOI:"]:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]
        
        # Validate DOI format (should start with 10.)
        if not doi.startswith("10."):
            return None
        
        return doi
    
    def _try_mirror(self, mirror: str, doi: str) -> Optional[str]:
        """Try to get PDF URL from a specific Sci-Hub mirror."""
        try:
            response = requests.get(
                f"{mirror}/{doi}",
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                allow_redirects=True,
            )
            
            if response.status_code != 200:
                return None
            
            # Find PDF embed URL in the page
            pdf_url = self._extract_pdf_url(response.text, mirror)
            return pdf_url
            
        except (requests.RequestException, Exception):
            return None
    
    def _extract_pdf_url(self, html: str, mirror: str) -> Optional[str]:
        """Extract PDF URL from Sci-Hub page HTML."""
        # Pattern 1: iframe or embed with PDF
        patterns = [
            r'<iframe[^>]+src=["\']([^"\']+\.pdf[^"\']*)["\']',
            r'<embed[^>]+src=["\']([^"\']+\.pdf[^"\']*)["\']',
            r'<a[^>]+href=["\']([^"\']+\.pdf[^"\']*)["\'][^>]*>.*?download',
            r'location\.href\s*=\s*["\']([^"\']+\.pdf[^"\']*)["\']',
            # Sci-Hub specific pattern
            r'<button[^>]+onclick=["\']location\.href=\'([^\']+)\'["\']',
            r'<iframe[^>]+src=["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                # Make URL absolute
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = mirror + url
                elif not url.startswith("http"):
                    url = mirror + "/" + url
                return url
        
        return None
