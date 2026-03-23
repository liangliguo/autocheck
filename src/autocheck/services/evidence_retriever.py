from __future__ import annotations

from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from autocheck.config.settings import AppSettings
from autocheck.schemas.models import ClaimRecord, EvidenceChunk, ReferenceEntry
from autocheck.utils.text import lexical_overlap_score


class EvidenceRetriever:
    def __init__(self, settings: AppSettings) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def retrieve(
        self,
        claim: ClaimRecord,
        reference: ReferenceEntry,
        paper_text: str,
        limit: int = 6,
    ) -> List[EvidenceChunk]:
        if not paper_text.strip():
            return []

        docs = self.splitter.split_documents(
            [
                Document(
                    page_content=paper_text,
                    metadata={"ref_id": reference.ref_id, "title": reference.title or ""},
                )
            ]
        )

        scored: List[EvidenceChunk] = []
        for index, doc in enumerate(docs, start=1):
            score = lexical_overlap_score(claim.text, doc.page_content)
            if score <= 0:
                continue
            scored.append(
                EvidenceChunk(
                    chunk_id=f"{reference.ref_id}#{index}",
                    ref_id=reference.ref_id,
                    source_title=reference.title,
                    score=score,
                    text=doc.page_content.strip(),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]
