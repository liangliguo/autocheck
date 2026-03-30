from __future__ import annotations

from typing import Iterable, Iterator, List

import requests

from autocheck.repository.library import PaperLibrary
from autocheck.resolvers.arxiv import ArxivResolver
from autocheck.resolvers.openalex import OpenAlexResolver
from autocheck.schemas.models import LocalPaperRecord, ReferenceEntry, ResolverMatch


class ReferenceManager:
    def __init__(self, library: PaperLibrary) -> None:
        self.library = library
        self.resolvers = [OpenAlexResolver(), ArxivResolver()]

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
        if not reference.title and not reference.arxiv_id:
            return self.library.mark_failure(reference, "not_found", "Missing title and arXiv id.")

        for resolver in self.resolvers:
            for candidate_reference in self._reference_candidates(reference):
                try:
                    match = resolver.locate(candidate_reference)
                except Exception as exc:
                    last_error = f"{resolver.name}: {exc}"
                    continue

                if not match or not match.pdf_url:
                    continue

                try:
                    pdf_bytes = self._download_pdf(match)
                    return self.library.save_download(reference, match, pdf_bytes)
                except Exception as exc:
                    last_error = f"{resolver.name}: {exc}"

        return self.library.mark_failure(
            reference,
            "not_found",
            locals().get("last_error", "No open-access PDF match found."),
        )

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
