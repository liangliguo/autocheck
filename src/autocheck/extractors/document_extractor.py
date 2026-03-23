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

        merged: List[ClaimRecord] = []
        for index, claim in enumerate(llm_claims, start=1):
            citation_markers = claim.citation_markers or extract_citation_markers(claim.text)
            merged.append(
                ClaimRecord(
                    claim_id=claim.claim_id or f"claim-{index}",
                    text=normalize_whitespace(claim.text),
                    citation_markers=dedupe_preserve_order(citation_markers),
                    section=claim.section,
                    paragraph_index=claim.paragraph_index or index,
                )
            )
        return merged

    def _merge_references(
        self,
        heuristic_references: List[ReferenceEntry],
        llm_references: List[ReferenceEntry],
    ) -> List[ReferenceEntry]:
        if not llm_references:
            return heuristic_references

        merged: List[ReferenceEntry] = []
        total = max(len(heuristic_references), len(llm_references))
        for index in range(1, total + 1):
            reference = llm_references[index - 1] if index - 1 < len(llm_references) else None
            fallback = heuristic_references[index - 1] if index - 1 < len(heuristic_references) else None
            if reference is None and fallback is not None:
                merged.append(fallback)
                continue
            if reference is None:
                continue
            merged.append(
                ReferenceEntry(
                    ref_id=reference.ref_id or (fallback.ref_id if fallback else f"ref-{index}"),
                    raw_text=reference.raw_text or (fallback.raw_text if fallback else ""),
                    title=reference.title or (fallback.title if fallback else None),
                    authors=reference.authors or (fallback.authors if fallback else []),
                    year=reference.year or (fallback.year if fallback else None),
                    doi=reference.doi or (fallback.doi if fallback else None),
                    arxiv_id=reference.arxiv_id or (fallback.arxiv_id if fallback else None),
                    aliases=reference.aliases or (fallback.aliases if fallback else []),
                )
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

        cleaned = re.sub(r"^(?:\[\d+\]|\d+\.)\s*", "", raw_text).strip()
        parts = [part.strip() for part in re.split(r"\.\s+", cleaned) if part.strip()]
        if len(parts) >= 2:
            return parts[1][:300]
        return None

    def _guess_authors(self, raw_text: str) -> List[str]:
        cleaned = re.sub(r"^(?:\[\d+\]|\d+\.)\s*", "", raw_text).strip()
        first_segment = re.split(r"\.\s+", cleaned, maxsplit=1)[0]
        candidates = re.split(r",| and ", first_segment)
        authors = [normalize_whitespace(candidate) for candidate in candidates if normalize_whitespace(candidate)]
        return authors[:8]

    def _guess_year(self, raw_text: str) -> Optional[int]:
        match = re.search(r"\b(19|20)\d{2}\b", raw_text)
        if match:
            return int(match.group(0))
        return None

    def _guess_arxiv_id(self, raw_text: str) -> Optional[str]:
        match = re.search(r"\barXiv:(\d{4}\.\d{4,5}(?:v\d+)?)\b", raw_text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return None
