from __future__ import annotations

from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from autocheck.prompts.templates import VERIFICATION_HUMAN_TEMPLATE, VERIFICATION_SYSTEM_PROMPT
from autocheck.repository.library import PaperLibrary
from autocheck.schemas.models import (
    ClaimCitationAssessment,
    ClaimRecord,
    LLMVerificationDecision,
    ReferenceEntry,
    VerificationLabel,
)
from autocheck.services.document_loader import DocumentLoader
from autocheck.services.evidence_retriever import EvidenceRetriever


class ClaimCitationVerifier:
    def __init__(
        self,
        library: PaperLibrary,
        retriever: EvidenceRetriever,
        chat_model: object | None,
    ) -> None:
        self.library = library
        self.retriever = retriever
        self.chat_model = chat_model
        self.loader = DocumentLoader()

    def verify(
        self,
        claim: ClaimRecord,
        citation_marker: str,
        reference: ReferenceEntry | None,
    ) -> ClaimCitationAssessment:
        if reference is None:
            return ClaimCitationAssessment(
                claim_id=claim.claim_id,
                claim_text=claim.text,
                citation_marker=citation_marker,
                verdict=VerificationLabel.NOT_FOUND,
                confidence=0.0,
                reasoning="Citation marker could not be matched to any parsed reference entry.",
            )

        record = self.library.get(reference)
        if record is None or (not record.pdf_path and not record.text_path):
            return ClaimCitationAssessment(
                claim_id=claim.claim_id,
                claim_text=claim.text,
                citation_marker=citation_marker,
                reference=reference,
                verdict=VerificationLabel.NOT_FOUND,
                confidence=0.0,
                reasoning="The cited source could not be downloaded or found in the local library.",
            )

        paper_text = self._load_paper_text(reference, record.pdf_path, record.text_path)
        if not paper_text.strip():
            return ClaimCitationAssessment(
                claim_id=claim.claim_id,
                claim_text=claim.text,
                citation_marker=citation_marker,
                reference=reference,
                verdict=VerificationLabel.NOT_FOUND,
                confidence=0.0,
                reasoning="The cited PDF was found, but text extraction produced no usable content.",
            )

        evidence = self.retriever.retrieve(claim, reference, paper_text)
        if not evidence:
            return ClaimCitationAssessment(
                claim_id=claim.claim_id,
                claim_text=claim.text,
                citation_marker=citation_marker,
                reference=reference,
                verdict=VerificationLabel.NOT_FOUND,
                confidence=0.0,
                reasoning="No relevant evidence chunk could be retrieved from the cited source.",
            )

        decision = self._verify_with_llm(claim, citation_marker, reference, evidence)
        evidence_map = {chunk.chunk_id: chunk for chunk in evidence}
        used_chunks = [evidence_map[chunk_id] for chunk_id in decision.used_chunk_ids if chunk_id in evidence_map]
        if not used_chunks:
            used_chunks = evidence[: min(3, len(evidence))]

        return ClaimCitationAssessment(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            citation_marker=citation_marker,
            reference=reference,
            verdict=decision.verdict,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
            evidence=used_chunks,
            supported_points=decision.supported_points,
            unsupported_points=decision.unsupported_points,
            concerns=decision.concerns,
        )

    def _load_paper_text(
        self,
        reference: ReferenceEntry,
        pdf_path: str | None,
        text_path: str | None,
    ) -> str:
        if text_path and Path(text_path).exists():
            return Path(text_path).read_text(encoding="utf-8", errors="ignore")

        if not pdf_path or not Path(pdf_path).exists():
            return ""

        text = self.loader.load_text(pdf_path)
        self.library.save_text(reference, text)
        return text

    def _verify_with_llm(
        self,
        claim: ClaimRecord,
        citation_marker: str,
        reference: ReferenceEntry,
        evidence,
    ) -> LLMVerificationDecision:
        if self.chat_model is None:
            return self._fallback_decision(
                evidence,
                reasoning="Fallback lexical scorer was used because no chat model was configured.",
                concern="LLM verification was skipped because no chat model was configured.",
            )

        prompt = ChatPromptTemplate.from_messages(
            [("system", VERIFICATION_SYSTEM_PROMPT), ("human", VERIFICATION_HUMAN_TEMPLATE)]
        )
        chain = prompt | self.chat_model.with_structured_output(
            LLMVerificationDecision,
            method="function_calling",
        )
        rendered_evidence = "\n\n".join(
            f"[{chunk.chunk_id}] score={chunk.score:.3f}\n{chunk.text}" for chunk in evidence
        )
        try:
            return chain.invoke(
                {
                    "claim_id": claim.claim_id,
                    "claim_text": claim.text,
                    "citation_marker": citation_marker,
                    "ref_id": reference.ref_id,
                    "title": reference.title or "",
                    "authors": ", ".join(reference.authors),
                    "year": reference.year or "",
                    "evidence": rendered_evidence,
                }
            )
        except Exception as exc:
            error_message = " ".join(str(exc).split())[:240]
            return self._fallback_decision(
                evidence,
                reasoning="Fallback lexical scorer was used because LLM verification failed.",
                concern=(
                    "LLM verification failed during structured parsing and fell back to lexical "
                    f"scoring: {error_message or type(exc).__name__}."
                ),
            )

    def _fallback_decision(
        self,
        evidence,
        reasoning: str,
        concern: str,
    ) -> LLMVerificationDecision:
        top_score = evidence[0].score
        if top_score >= 0.45:
            verdict = VerificationLabel.STRONG_SUPPORT
        elif top_score >= 0.2:
            verdict = VerificationLabel.PARTIAL_SUPPORT
        else:
            verdict = VerificationLabel.UNSUPPORTED_OR_MISLEADING

        return LLMVerificationDecision(
            verdict=verdict,
            confidence=min(0.8, max(0.2, top_score)),
            reasoning=reasoning,
            used_chunk_ids=[chunk.chunk_id for chunk in evidence[:2]],
            supported_points=[],
            unsupported_points=[],
            concerns=[concern],
        )
