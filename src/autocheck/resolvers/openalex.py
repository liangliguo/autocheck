from __future__ import annotations

from typing import Optional

import requests

from autocheck.schemas.models import ReferenceEntry, ResolverMatch
from autocheck.utils.text import lexical_overlap_score


class OpenAlexResolver:
    name = "openalex"
    api_url = "https://api.openalex.org/works"

    def locate(self, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        if not reference.title:
            return None

        response = requests.get(
            self.api_url,
            params={"search": reference.title, "per-page": 5},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])

        best_match: Optional[ResolverMatch] = None
        for result in results:
            title = result.get("display_name") or ""
            authors = [
                authorship.get("author", {}).get("display_name", "")
                for authorship in result.get("authorships", [])
                if authorship.get("author", {}).get("display_name")
            ]
            open_access = result.get("open_access") or {}
            best_location = result.get("best_oa_location") or {}
            pdf_url = best_location.get("pdf_url") or open_access.get("oa_url")
            score = lexical_overlap_score(reference.title, title)
            if reference.authors and authors:
                overlap = len(
                    {name.split()[-1].lower() for name in reference.authors}
                    & {name.split()[-1].lower() for name in authors}
                )
                score = min(1.0, score + (0.05 * overlap))

            candidate = ResolverMatch(
                resolver_name=self.name,
                title=title,
                authors=authors,
                year=result.get("publication_year"),
                pdf_url=pdf_url,
                landing_page_url=result.get("id"),
                external_id=result.get("doi") or result.get("id"),
                score=score,
            )
            if not best_match or candidate.score > best_match.score:
                best_match = candidate

        return best_match if best_match and best_match.score >= 0.2 else None
