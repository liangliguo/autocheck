from __future__ import annotations

from typing import Optional

import requests

from autocheck.schemas.models import ReferenceEntry, ResolverMatch
from autocheck.utils.text import lexical_overlap_score


class CrossRefResolver:
    """
    Resolver that searches CrossRef for paper metadata and DOIs.
    
    CrossRef is a comprehensive database of academic papers with DOIs.
    This resolver can find DOIs for papers by title, which can then be
    used with Sci-Hub for downloading.
    """
    
    name = "crossref"
    api_url = "https://api.crossref.org/works"
    
    def locate(self, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        """Search CrossRef for a paper by title or DOI."""
        # If we already have a DOI, just verify it
        if reference.doi:
            return self._lookup_by_doi(reference)
        
        # Search by title
        if reference.title:
            return self._search_by_title(reference)
        
        return None
    
    def _lookup_by_doi(self, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        """Look up a paper by its DOI."""
        doi = self._normalize_doi(reference.doi)
        if not doi:
            return None
        
        try:
            response = requests.get(
                f"{self.api_url}/{doi}",
                timeout=15,
                headers={"User-Agent": "AutoCheck/1.0 (mailto:autocheck@example.com)"},
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            work = data.get("message", {})
            return self._work_to_match(work, reference)
            
        except (requests.RequestException, Exception):
            return None
    
    def _search_by_title(self, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        """Search CrossRef for a paper by title."""
        try:
            params = {
                "query.title": reference.title,
                "rows": 5,
            }
            
            # Add author filter if available
            if reference.authors:
                params["query.author"] = " ".join(reference.authors[:2])
            
            response = requests.get(
                self.api_url,
                params=params,
                timeout=15,
                headers={"User-Agent": "AutoCheck/1.0 (mailto:autocheck@example.com)"},
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            items = data.get("message", {}).get("items", [])
            
            best_match: Optional[ResolverMatch] = None
            for item in items:
                match = self._work_to_match(item, reference)
                if match and (not best_match or match.score > best_match.score):
                    best_match = match
            
            return best_match if best_match and best_match.score >= 0.3 else None
            
        except (requests.RequestException, Exception):
            return None
    
    def _work_to_match(self, work: dict, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        """Convert a CrossRef work object to a ResolverMatch."""
        if not work:
            return None
        
        # Extract title
        titles = work.get("title", [])
        title = titles[0] if titles else None
        
        # Extract authors
        authors = []
        for author in work.get("author", []):
            name_parts = []
            if author.get("given"):
                name_parts.append(author["given"])
            if author.get("family"):
                name_parts.append(author["family"])
            if name_parts:
                authors.append(" ".join(name_parts))
        
        # Extract year
        year = None
        published = work.get("published-print") or work.get("published-online") or work.get("created")
        if published:
            date_parts = published.get("date-parts", [[]])
            if date_parts and date_parts[0]:
                year = date_parts[0][0]
        
        # Extract DOI
        doi = work.get("DOI")
        
        # Extract PDF link (CrossRef may have it)
        pdf_url = None
        for link in work.get("link", []):
            if link.get("content-type") == "application/pdf":
                pdf_url = link.get("URL")
                break
        
        # Calculate score
        score = 0.0
        if title and reference.title:
            score = lexical_overlap_score(reference.title, title)
        elif doi and reference.doi and self._normalize_doi(doi) == self._normalize_doi(reference.doi):
            score = 1.0
        
        if score < 0.2:
            return None
        
        return ResolverMatch(
            resolver_name=self.name,
            title=title,
            authors=authors,
            year=year,
            pdf_url=pdf_url,
            landing_page_url=f"https://doi.org/{doi}" if doi else None,
            external_id=f"doi:{doi}" if doi else None,
            score=score,
        )
    
    def _normalize_doi(self, doi: str | None) -> Optional[str]:
        """Normalize DOI format."""
        if not doi:
            return None
        
        doi = doi.strip()
        for prefix in ["https://doi.org/", "http://doi.org/", "doi:", "DOI:"]:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]
        
        return doi.lower() if doi.startswith("10.") else None
