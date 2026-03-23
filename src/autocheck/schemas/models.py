from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class VerificationLabel(str, Enum):
    STRONG_SUPPORT = "strong_support"
    PARTIAL_SUPPORT = "partial_support"
    UNSUPPORTED_OR_MISLEADING = "unsupported_or_misleading"
    NOT_FOUND = "not_found"


class ReferenceEntry(BaseModel):
    ref_id: str
    raw_text: str
    title: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)


class ClaimRecord(BaseModel):
    claim_id: str
    text: str
    citation_markers: List[str] = Field(default_factory=list)
    section: Optional[str] = None
    paragraph_index: Optional[int] = None


class ParsedDocument(BaseModel):
    source_path: str
    body_text: str
    references_text: str
    claims: List[ClaimRecord] = Field(default_factory=list)
    references: List[ReferenceEntry] = Field(default_factory=list)


class ResolverMatch(BaseModel):
    resolver_name: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    pdf_url: Optional[str] = None
    landing_page_url: Optional[str] = None
    external_id: Optional[str] = None
    score: float = 0.0


class LocalPaperRecord(BaseModel):
    ref_id: str
    title: Optional[str] = None
    pdf_path: Optional[str] = None
    text_path: Optional[str] = None
    source_url: Optional[str] = None
    resolver_name: Optional[str] = None
    status: str = "pending"
    note: Optional[str] = None


class EvidenceChunk(BaseModel):
    chunk_id: str
    ref_id: str
    source_title: Optional[str] = None
    score: float
    text: str


class LLMClaimExtraction(BaseModel):
    claims: List[ClaimRecord] = Field(default_factory=list)
    references: List[ReferenceEntry] = Field(default_factory=list)


class LLMVerificationDecision(BaseModel):
    verdict: VerificationLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    used_chunk_ids: List[str] = Field(default_factory=list)
    supported_points: List[str] = Field(default_factory=list)
    unsupported_points: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)


class ClaimCitationAssessment(BaseModel):
    claim_id: str
    claim_text: str
    citation_marker: str
    reference: Optional[ReferenceEntry] = None
    verdict: VerificationLabel
    confidence: float = 0.0
    reasoning: str
    evidence: List[EvidenceChunk] = Field(default_factory=list)
    supported_points: List[str] = Field(default_factory=list)
    unsupported_points: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)


class ReportSummary(BaseModel):
    total_claims: int
    total_assessments: int
    strong_support: int
    partial_support: int
    unsupported_or_misleading: int
    not_found: int


class VerificationReport(BaseModel):
    source_path: str
    generated_at: datetime
    summary: ReportSummary
    parsed_document: ParsedDocument
    local_library: List[LocalPaperRecord]
    assessments: List[ClaimCitationAssessment]


class PipelineEvent(BaseModel):
    event: str
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
