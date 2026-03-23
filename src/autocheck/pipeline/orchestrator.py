from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Tuple

from autocheck.config.settings import AppSettings
from autocheck.extractors.document_extractor import DocumentClaimReferenceExtractor
from autocheck.llm.factory import build_chat_model
from autocheck.pipeline.verifier import ClaimCitationVerifier
from autocheck.repository.library import PaperLibrary
from autocheck.schemas.models import (
    ClaimCitationAssessment,
    ClaimRecord,
    PipelineEvent,
    ParsedDocument,
    ReferenceEntry,
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
        self._last_run_result: tuple[VerificationReport, Dict[str, Path]] | None = None

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
        for _event in self.run_incremental(
            source_path=source_path,
            report_dir=report_dir,
            skip_download=skip_download,
        ):
            pass

        if self._last_run_result is None:
            raise RuntimeError("Pipeline completed without producing a final result.")
        return self._last_run_result

    def run_incremental(
        self,
        source_path: str | Path,
        report_dir: str | Path | None = None,
        skip_download: bool = False,
    ) -> Iterator[PipelineEvent]:
        self._last_run_result = None
        source = Path(source_path)
        output_dir = Path(report_dir) if report_dir else self.settings.reports_dir
        stem = slugify(source.stem, fallback="report")
        paths = self.report_writer.initialize_incremental_output(output_dir, stem)

        yield self._emit_event(
            paths["events"],
            "stage_started",
            {"stage": "extract", "source_path": str(source.resolve())},
        )
        parsed_document = self.extractor.extract(source)
        yield self._emit_event(
            paths["events"],
            "stage_completed",
            {
                "stage": "extract",
                "total_claims": len(parsed_document.claims),
                "total_references": len(parsed_document.references),
            },
        )

        total_assessments = self._estimate_assessment_count(parsed_document)
        unmatched_tasks, reference_tasks = self._build_assessment_tasks(parsed_document)
        local_records = []
        total_references = len(parsed_document.references)
        yield self._emit_event(
            paths["events"],
            "stage_started",
            {
                "stage": "resolve_references",
                "total_references": total_references,
                "skip_download": skip_download,
            },
        )
        yield self._emit_event(
            paths["events"],
            "stage_started",
            {
                "stage": "verify",
                "total_assessments": total_assessments,
                "mode": "streaming_by_reference",
            },
        )

        assessments = []
        assessment_index = 0
        for claim, marker, reference in unmatched_tasks:
            assessment = self.verifier.verify(claim, marker, reference)
            assessments.append(assessment)
            assessment_index += 1
            yield self._emit_event(
                paths["events"],
                "assessment_ready",
                {
                    "stage": "verify",
                    "current": assessment_index,
                    "total": total_assessments,
                    "assessment": assessment.model_dump(mode="json"),
                },
            )

        for index, record in enumerate(
            self.reference_manager.iter_prepare_references(
                parsed_document.references,
                skip_download=skip_download,
            ),
            start=1,
        ):
            local_records.append(record)
            yield self._emit_event(
                paths["events"],
                "reference_processed",
                {
                    "stage": "resolve_references",
                    "current": index,
                    "total": total_references,
                    "record": record.model_dump(mode="json"),
                },
            )

            for claim, marker, reference in reference_tasks.get(record.ref_id, []):
                assessment = self.verifier.verify(claim, marker, reference)
                assessments.append(assessment)
                assessment_index += 1
                yield self._emit_event(
                    paths["events"],
                    "assessment_ready",
                    {
                        "stage": "verify",
                        "current": assessment_index,
                        "total": total_assessments,
                        "assessment": assessment.model_dump(mode="json"),
                    },
                )

        yield self._emit_event(
            paths["events"],
            "stage_completed",
            {
                "stage": "resolve_references",
                "total_references": total_references,
                "resolved": sum(1 for record in local_records if record.status in {"cached", "downloaded", "processed"}),
                "not_found": sum(1 for record in local_records if record.status == "not_found"),
                "skipped": sum(1 for record in local_records if record.status == "skipped"),
            },
        )

        summary = self._summarize(parsed_document, assessments)
        yield self._emit_event(
            paths["events"],
            "stage_completed",
            {
                "stage": "verify",
                "summary": summary.model_dump(mode="json"),
            },
        )

        yield self._emit_event(
            paths["events"],
            "stage_started",
            {"stage": "write_report"},
        )
        report = VerificationReport(
            source_path=str(source.resolve()),
            generated_at=datetime.utcnow(),
            summary=summary,
            parsed_document=parsed_document,
            local_library=local_records,
            assessments=assessments,
        )
        paths = self.report_writer.write(report, output_dir, stem, paths=paths)
        self._last_run_result = (report, paths)
        yield self._emit_event(
            paths["events"],
            "report_completed",
            {
                "stage": "write_report",
                "summary": summary.model_dump(mode="json"),
                "report_paths": {key: str(value) for key, value in paths.items()},
            },
        )

    def _build_assessment_tasks(
        self,
        parsed_document: ParsedDocument,
    ) -> tuple[
        list[tuple[ClaimRecord, str, ReferenceEntry | None]],
        dict[str, list[tuple[ClaimRecord, str, ReferenceEntry | None]]],
    ]:
        unmatched_tasks: list[tuple[ClaimRecord, str, ReferenceEntry | None]] = []
        reference_tasks: dict[str, list[tuple[ClaimRecord, str, ReferenceEntry | None]]] = {}

        for claim in parsed_document.claims:
            if not claim.citation_markers:
                continue
            for marker in claim.citation_markers:
                reference = match_citation_to_reference(marker, parsed_document.references)
                task = (claim, marker, reference)
                if reference is None:
                    unmatched_tasks.append(task)
                    continue
                reference_tasks.setdefault(reference.ref_id, []).append(task)

        return unmatched_tasks, reference_tasks

    def _estimate_assessment_count(self, parsed_document: ParsedDocument) -> int:
        return sum(len(claim.citation_markers) for claim in parsed_document.claims)

    def _emit_event(
        self,
        events_path: Path,
        event_name: str,
        payload: dict,
    ) -> PipelineEvent:
        event = PipelineEvent(
            event=event_name,
            timestamp=datetime.utcnow(),
            payload=payload,
        )
        self.report_writer.append_event(events_path, event)
        return event

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
