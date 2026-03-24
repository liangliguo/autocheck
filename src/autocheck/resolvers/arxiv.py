from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

import requests

from autocheck.schemas.models import ReferenceEntry, ResolverMatch
from autocheck.utils.text import lexical_overlap_score


class ArxivResolver:
    name = "arxiv"
    api_url = "http://export.arxiv.org/api/query"

    def locate(self, reference: ReferenceEntry) -> Optional[ResolverMatch]:
        params = {"max_results": 5}
        if reference.arxiv_id:
            params["id_list"] = reference.arxiv_id
        elif reference.title:
            params["search_query"] = f'ti:"{reference.title}"'
        else:
            return None

        response = requests.get(self.api_url, params=params, timeout=20)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", namespace)

        best_match: Optional[ResolverMatch] = None
        for entry in entries:
            title = (entry.findtext("atom:title", default="", namespaces=namespace) or "").strip()
            authors = [
                (author.findtext("atom:name", default="", namespaces=namespace) or "").strip()
                for author in entry.findall("atom:author", namespace)
            ]
            published = entry.findtext("atom:published", default="", namespaces=namespace)
            year = int(published[:4]) if published[:4].isdigit() else None
            entry_id = entry.findtext("atom:id", default="", namespaces=namespace)
            pdf_url = self._find_pdf_url(entry, namespace, entry_id)
            score = lexical_overlap_score(reference.title or "", title)

            candidate = ResolverMatch(
                resolver_name=self.name,
                title=title,
                authors=[author for author in authors if author],
                year=year,
                pdf_url=pdf_url,
                landing_page_url=entry_id or None,
                external_id=reference.arxiv_id or entry_id.rsplit("/", 1)[-1] or None,
                score=score,
            )
            if not best_match or candidate.score > best_match.score:
                best_match = candidate

        return best_match if best_match and (reference.arxiv_id or best_match.score >= 0.2) else None

    def _find_pdf_url(
        self,
        entry: ET.Element,
        namespace: dict,
        entry_id: str,
    ) -> Optional[str]:
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("title") == "pdf":
                return link.attrib.get("href")
        if entry_id:
            return entry_id.replace("/abs/", "/pdf/") + ".pdf"
        return None
