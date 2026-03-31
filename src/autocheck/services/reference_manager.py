from __future__ import annotations

from typing import Iterable, Iterator, List

import requests

from autocheck.repository.library import PaperLibrary
from autocheck.resolvers.arxiv import ArxivResolver
from autocheck.resolvers.crossref import CrossRefResolver
from autocheck.resolvers.openalex import OpenAlexResolver
from autocheck.resolvers.scihub import SciHubResolver
from autocheck.schemas.models import LocalPaperRecord, ReferenceEntry, ResolverMatch


class ReferenceManager:
    def __init__(self, library: PaperLibrary) -> None:
        self.library = library
        # Order: OpenAlex (open access), arXiv, CrossRef (metadata), Sci-Hub (last resort)
        self.metadata_resolvers = [OpenAlexResolver(), ArxivResolver(), CrossRefResolver()]
        self.download_resolvers = [SciHubResolver()]

    def prepare_references(
        self,
        references: Iterable[ReferenceEntry],
        skip_download: bool = False,
    ) -> List[LocalPaperRecord]:
        return list(self.iter_prepare_references(references, skip_download=skip_download))

    def iter_prepare_references(
        self,
        references: Iterable[ReferenceEntry],
        skip_download: bool = False,
    ) -> Iterator[LocalPaperRecord]:
        records: List[LocalPaperRecord] = []
        for reference in references:
            existing = self.library.get(reference)
            if existing and existing.text_path:
                existing.status = "processed"
                self.library.ensure_placeholder(reference, status="processed")
                records.append(existing)
                yield existing
                continue

            if existing and existing.pdf_path:
                existing.status = "cached"
                self.library.ensure_placeholder(reference, status="cached")
                records.append(existing)
                yield existing
                continue

            if skip_download:
                record = self.library.ensure_placeholder(
                    reference,
                    status="skipped",
                    note="Download skipped by user option.",
                )
                records.append(record)
                yield record
                continue

            record = self._download_reference(reference)
            records.append(record)
            yield record

    def _download_reference(self, reference: ReferenceEntry) -> LocalPaperRecord:
        if not reference.title and not reference.arxiv_id and not reference.doi:
            return self.library.mark_failure(reference, "not_found", "Missing title, arXiv id, and DOI.")

        last_error = "No PDF source found."
        found_match: ResolverMatch | None = None

        # Phase 1: Try metadata resolvers (OpenAlex, arXiv, CrossRef) which may have PDFs
        for resolver in self.metadata_resolvers:
            for candidate_reference in self._reference_candidates(reference):
                try:
                    match = resolver.locate(candidate_reference)
                except Exception as exc:
                    last_error = f"{resolver.name}: {exc}"
                    continue

                if not match:
                    continue

                # If match has PDF, try to download it
                if match.pdf_url:
                    try:
                        pdf_bytes = self._download_pdf(match)
                        return self.library.save_download(reference, match, pdf_bytes)
                    except Exception as exc:
                        last_error = f"{resolver.name}: {exc}"
                
                # Keep the match for DOI-based fallback
                if match.external_id and match.external_id.startswith("doi:"):
                    found_match = match

        # Phase 2: If we have a DOI (from reference or found match), try Sci-Hub
        doi_to_try = reference.doi
        if not doi_to_try and found_match and found_match.external_id:
            doi_to_try = found_match.external_id.replace("doi:", "")
        
        if doi_to_try:
            doi_reference = reference.model_copy(update={"doi": doi_to_try})
            for resolver in self.download_resolvers:
                try:
                    match = resolver.locate(doi_reference)
                except Exception as exc:
                    last_error = f"{resolver.name}: {exc}"
                    continue

                if match and match.pdf_url:
                    try:
                        pdf_bytes = self._download_pdf(match)
                        # Use found_match metadata if available
                        final_match = match
                        if found_match:
                            final_match = match.model_copy(update={
                                "title": found_match.title or match.title,
                                "authors": found_match.authors or match.authors,
                                "year": found_match.year or match.year,
                            })
                        return self.library.save_download(reference, final_match, pdf_bytes)
                    except Exception as exc:
                        last_error = f"{resolver.name}: {exc}"

        return self.library.mark_failure(reference, "not_found", last_error)

    def _download_pdf(self, match: ResolverMatch) -> bytes:
        response = requests.get(match.pdf_url, timeout=60)
        response.raise_for_status()
        pdf_bytes = response.content
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("Downloaded content is not a PDF.")
        return pdf_bytes

    def _reference_candidates(self, reference: ReferenceEntry) -> Iterator[ReferenceEntry]:
        yield reference
        if not reference.title:
            return

        normalized_title = " ".join(reference.title.split())
        seen_titles = {normalized_title}
        for candidate_title in (
            normalized_title.lower(),
            normalized_title.upper(),
            normalized_title.title(),
        ):
            if candidate_title in seen_titles:
                continue
            seen_titles.add(candidate_title)
            yield reference.model_copy(update={"title": candidate_title})
