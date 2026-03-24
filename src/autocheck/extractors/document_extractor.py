from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate

from autocheck.prompts.templates import EXTRACTION_HUMAN_TEMPLATE, EXTRACTION_SYSTEM_PROMPT
from autocheck.schemas.models import ClaimRecord, LLMClaimExtraction, ParsedDocument, ReferenceEntry
from autocheck.services.document_loader import DocumentLoader
from autocheck.utils.citations import (
    build_reference_aliases,
    extract_citation_markers,
    extract_cited_sentences,
    split_reference_entries,
    split_references_section,
)
from autocheck.utils.text import dedupe_preserve_order, normalize_whitespace


class DocumentClaimReferenceExtractor:
    def __init__(self, chat_model: object | None) -> None:
        self.chat_model = chat_model
        self.loader = DocumentLoader()

    def extract(self, source_path: str | Path) -> ParsedDocument:
        path = Path(source_path)
        full_text = self.loader.load_text(path)
        body_text, references_text = split_references_section(full_text)

        candidate_sentences = extract_cited_sentences(body_text)
        raw_reference_entries = split_reference_entries(references_text)

        heuristic_claims = self._build_heuristic_claims(candidate_sentences)
        heuristic_references = self._build_heuristic_references(raw_reference_entries)

        claims = heuristic_claims
        references = heuristic_references

        if self.chat_model and (candidate_sentences or raw_reference_entries):
            llm_output = self._extract_with_llm(path, candidate_sentences, raw_reference_entries)
            if llm_output:
                claims = self._merge_claims(heuristic_claims, llm_output.claims)
                references = self._merge_references(heuristic_references, llm_output.references)

        references = [self._finalize_reference(reference, index) for index, reference in enumerate(references, start=1)]
        claims = [self._finalize_claim(claim, index) for index, claim in enumerate(claims, start=1)]

        return ParsedDocument(
            source_path=str(path.resolve()),
            body_text=body_text,
            references_text=references_text,
            claims=claims,
            references=references,
        )

    def _extract_with_llm(
        self,
        source_path: Path,
        candidate_sentences: List[str],
        raw_reference_entries: List[str],
    ) -> Optional[LLMClaimExtraction]:
        try:
            prompt = ChatPromptTemplate.from_messages(
                [("system", EXTRACTION_SYSTEM_PROMPT), ("human", EXTRACTION_HUMAN_TEMPLATE)]
            )
            chain = prompt | self.chat_model.with_structured_output(LLMClaimExtraction)
            return chain.invoke(
                {
                    "source_path": str(source_path),
                    "candidate_sentences": "\n".join(
                        f"- {sentence}" for sentence in candidate_sentences[:120]
                    )
                    or "(none)",
                    "raw_references": "\n".join(
                        f"- {reference}" for reference in raw_reference_entries[:120]
                    )
                    or "(none)",
                }
            )
        except Exception:
            return None

    def _build_heuristic_claims(self, candidate_sentences: List[str]) -> List[ClaimRecord]:
        claims: List[ClaimRecord] = []
        for index, sentence in enumerate(candidate_sentences, start=1):
            claims.append(
                ClaimRecord(
                    claim_id=f"claim-{index}",
                    text=normalize_whitespace(sentence),
                    citation_markers=extract_citation_markers(sentence),
                    paragraph_index=index,
                )
            )
        return claims

    def _build_heuristic_references(self, entries: List[str]) -> List[ReferenceEntry]:
        references: List[ReferenceEntry] = []
        for index, raw_text in enumerate(entries, start=1):
            ref_id = self._reference_id_from_text(raw_text, index)
            references.append(
                ReferenceEntry(
                    ref_id=ref_id,
                    raw_text=raw_text,
                    title=self._guess_title(raw_text),
                    authors=self._guess_authors(raw_text),
                    year=self._guess_year(raw_text),
                    arxiv_id=self._guess_arxiv_id(raw_text),
                    aliases=[ref_id],
                )
            )
        return references

    def _merge_claims(
        self,
        heuristic_claims: List[ClaimRecord],
        llm_claims: List[ClaimRecord],
    ) -> List[ClaimRecord]:
        if not llm_claims:
            return heuristic_claims

        merged = [
            self._finalize_claim(claim, index)
            for index, claim in enumerate(heuristic_claims, start=1)
        ]
        index_by_text = {
            normalize_whitespace(claim.text): position
            for position, claim in enumerate(merged)
        }

        for claim in llm_claims:
            normalized_text = normalize_whitespace(claim.text)
            existing_index = index_by_text.get(normalized_text)
            if existing_index is None:
                merged.append(
                    self._finalize_claim(
                        claim,
                        index=len(merged) + 1,
                    )
                )
                index_by_text[normalized_text] = len(merged) - 1
                continue

            existing = merged[existing_index]
            citation_markers = dedupe_preserve_order(
                existing.citation_markers
                + (claim.citation_markers or extract_citation_markers(claim.text))
            )
            merged[existing_index] = ClaimRecord(
                claim_id=existing.claim_id,
                text=existing.text,
                citation_markers=citation_markers,
                section=claim.section or existing.section,
                paragraph_index=claim.paragraph_index or existing.paragraph_index,
            )
        return merged

    def _merge_references(
        self,
        heuristic_references: List[ReferenceEntry],
        llm_references: List[ReferenceEntry],
    ) -> List[ReferenceEntry]:
        if not llm_references:
            return heuristic_references

        merged = [
            self._finalize_reference(reference, index)
            for index, reference in enumerate(heuristic_references, start=1)
        ]
        index_by_ref_id = {
            reference.ref_id: position
            for position, reference in enumerate(merged)
        }
        index_by_arxiv_id = {
            reference.arxiv_id: position
            for position, reference in enumerate(merged)
            if reference.arxiv_id
        }
        index_by_title = {
            normalize_whitespace(reference.title).lower(): position
            for position, reference in enumerate(merged)
            if reference.title
        }

        for reference in llm_references:
            normalized = self._finalize_reference(reference, index=len(merged) + 1)
            existing_index = index_by_ref_id.get(normalized.ref_id)
            if existing_index is None and normalized.arxiv_id:
                existing_index = index_by_arxiv_id.get(normalized.arxiv_id)
            if existing_index is None and normalized.title:
                existing_index = index_by_title.get(normalized.title.lower())

            if existing_index is None:
                merged.append(normalized)
                index_by_ref_id[normalized.ref_id] = len(merged) - 1
                if normalized.arxiv_id:
                    index_by_arxiv_id[normalized.arxiv_id] = len(merged) - 1
                if normalized.title:
                    index_by_title[normalized.title.lower()] = len(merged) - 1
                continue

            fallback = merged[existing_index]
            merged_reference = ReferenceEntry(
                ref_id=fallback.ref_id,
                raw_text=normalized.raw_text or fallback.raw_text,
                title=normalized.title or fallback.title,
                authors=normalized.authors or fallback.authors,
                year=normalized.year or fallback.year,
                doi=normalized.doi or fallback.doi,
                arxiv_id=normalized.arxiv_id or fallback.arxiv_id,
                aliases=dedupe_preserve_order(fallback.aliases + normalized.aliases),
            )
            merged[existing_index] = self._finalize_reference(
                merged_reference,
                index=existing_index + 1,
            )
        return merged

    def _finalize_reference(self, reference: ReferenceEntry, index: int) -> ReferenceEntry:
        ref_id = reference.ref_id or self._reference_id_from_text(reference.raw_text, index)
        finalized = ReferenceEntry(
            ref_id=ref_id,
            raw_text=normalize_whitespace(reference.raw_text),
            title=normalize_whitespace(reference.title) if reference.title else None,
            authors=[normalize_whitespace(author) for author in reference.authors if normalize_whitespace(author)],
            year=reference.year,
            doi=reference.doi,
            arxiv_id=reference.arxiv_id,
            aliases=reference.aliases,
        )
        finalized.aliases = build_reference_aliases(finalized)
        return finalized

    def _finalize_claim(self, claim: ClaimRecord, index: int) -> ClaimRecord:
        markers = claim.citation_markers or extract_citation_markers(claim.text)
        return ClaimRecord(
            claim_id=claim.claim_id or f"claim-{index}",
            text=normalize_whitespace(claim.text),
            citation_markers=dedupe_preserve_order(markers),
            section=claim.section,
            paragraph_index=claim.paragraph_index or index,
        )

    def _reference_id_from_text(self, text: str, index: int) -> str:
        match = re.match(r"^\[(\d+)\]", text.strip()) or re.match(r"^(\d+)\.", text.strip())
        if match:
            return f"[{match.group(1)}]"
        return f"ref-{index}"

    def _guess_title(self, raw_text: str) -> Optional[str]:
        quoted = re.search(r"[\"“](.+?)[\"”]", raw_text)
        if quoted:
            return quoted.group(1).strip()

        cleaned = re.sub(
            r"^(?:\[\d+\]|\d+\.)\s*",
            "",
            self._normalize_reference_text_for_parsing(raw_text),
        ).strip()
        parts = self._split_reference_segments(cleaned)
        if len(parts) >= 2:
            return parts[1][:300]
        return None

    def _guess_authors(self, raw_text: str) -> List[str]:
        cleaned = re.sub(
            r"^(?:\[\d+\]|\d+\.)\s*",
            "",
            self._normalize_reference_text_for_parsing(raw_text),
        ).strip()
        segments = self._split_reference_segments(cleaned)
        if not segments:
            return []
        first_segment = segments[0]
        candidates = re.split(r",| and ", first_segment)
        authors = [normalize_whitespace(candidate) for candidate in candidates if normalize_whitespace(candidate)]
        return authors[:8]

    def _guess_year(self, raw_text: str) -> Optional[int]:
        match = re.search(r"\b(19|20)\d{2}\b", raw_text)
        if match:
            return int(match.group(0))
        return None

    def _guess_arxiv_id(self, raw_text: str) -> Optional[str]:
        match = re.search(
            r"\b(?:arXiv:|abs/)(\d{4}\.\d{4,5}(?:v\d+)?)\b",
            raw_text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return None

    def _normalize_reference_text_for_parsing(self, raw_text: str) -> str:
        return re.sub(r"\b([A-Z])\s*\.\s*", r"\1. ", raw_text)

    def _split_reference_segments(self, text: str) -> List[str]:
        return [
            part.strip()
            for part in re.split(r"(?<!\b[A-Z])\.\s+", text)
            if part.strip()
        ]
