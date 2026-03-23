from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

from autocheck.config.settings import AppSettings
from autocheck.extractors.document_extractor import DocumentClaimReferenceExtractor
from autocheck.llm.factory import build_chat_model
from autocheck.pipeline.verifier import ClaimCitationVerifier
from autocheck.repository.library import PaperLibrary
from autocheck.schemas.models import (
    ClaimCitationAssessment,
    ParsedDocument,
    ReportSummary,
    VerificationLabel,
    VerificationReport,
)
from autocheck.services.evidence_retriever import EvidenceRetriever
from autocheck.services.reference_manager import ReferenceManager
from autocheck.services.report_writer import ReportWriter
from autocheck.utils.citations import match_citation_to_reference
from autocheck.utils.text import slugify


class AutoCheckPipeline:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.settings.ensure_directories()

        extract_model = (
            build_chat_model(settings, purpose="extract")
            if settings.enable_llm_extraction
            else None
        )
        verify_model = (
            build_chat_model(settings, purpose="verify")
            if settings.enable_llm_verification
            else None
        )

        self.extractor = DocumentClaimReferenceExtractor(extract_model)
        self.library = PaperLibrary(settings.downloads_dir, settings.processed_dir)
        self.reference_manager = ReferenceManager(self.library)
        self.retriever = EvidenceRetriever(settings)
        self.verifier = ClaimCitationVerifier(self.library, self.retriever, verify_model)
        self.report_writer = ReportWriter()

    def run(
        self,
        source_path: str | Path,
        report_dir: str | Path | None = None,
        skip_download: bool = False,
    ) -> Tuple[VerificationReport, Dict[str, Path]]:
        print(f"[AutoCheck] Extracting claims and references from {Path(source_path).name}...")
        parsed_document = self.extractor.extract(source_path)
        print(
            "[AutoCheck] Parsed "
            f"{len(parsed_document.claims)} claims and {len(parsed_document.references)} references."
        )
        print("[AutoCheck] Resolving and downloading cited references...")
        local_records = self.reference_manager.prepare_references(
            parsed_document.references,
            skip_download=skip_download,
        )

        print("[AutoCheck] Verifying claim-reference pairs...")
        assessments = self._assess(parsed_document)
        report = VerificationReport(
            source_path=str(Path(source_path).resolve()),
            generated_at=datetime.utcnow(),
            summary=self._summarize(parsed_document, assessments),
            parsed_document=parsed_document,
            local_library=local_records,
            assessments=assessments,
        )

        output_dir = Path(report_dir) if report_dir else self.settings.reports_dir
        stem = slugify(Path(source_path).stem, fallback="report")
        print("[AutoCheck] Writing reports...")
        paths = self.report_writer.write(report, output_dir, stem)
        return report, paths

    def _assess(self, parsed_document: ParsedDocument) -> list[ClaimCitationAssessment]:
        assessments: list[ClaimCitationAssessment] = []
        for claim in parsed_document.claims:
            if not claim.citation_markers:
                continue
            for marker in claim.citation_markers:
                reference = match_citation_to_reference(marker, parsed_document.references)
                assessments.append(self.verifier.verify(claim, marker, reference))
        return assessments

    def _summarize(
        self,
        parsed_document: ParsedDocument,
        assessments: list[ClaimCitationAssessment],
    ) -> ReportSummary:
        counts = {
            VerificationLabel.STRONG_SUPPORT: 0,
            VerificationLabel.PARTIAL_SUPPORT: 0,
            VerificationLabel.UNSUPPORTED_OR_MISLEADING: 0,
            VerificationLabel.NOT_FOUND: 0,
        }
        for assessment in assessments:
            counts[assessment.verdict] += 1

        return ReportSummary(
            total_claims=len(parsed_document.claims),
            total_assessments=len(assessments),
            strong_support=counts[VerificationLabel.STRONG_SUPPORT],
            partial_support=counts[VerificationLabel.PARTIAL_SUPPORT],
            unsupported_or_misleading=counts[VerificationLabel.UNSUPPORTED_OR_MISLEADING],
            not_found=counts[VerificationLabel.NOT_FOUND],
        )
