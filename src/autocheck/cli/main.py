from __future__ import annotations

import argparse
from pathlib import Path

from autocheck.config.settings import AppSettings
from autocheck.pipeline.orchestrator import AutoCheckPipeline
from autocheck.schemas.models import PipelineEvent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocheck",
        description="Verify whether paper claims are supported by their cited references.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full verification pipeline.")
    run_parser.add_argument("source", help="Path or URL to the PDF or text manuscript.")
    run_parser.add_argument(
        "-o",
        "--report-dir",
        default=None,
        help="Directory where JSON and Markdown reports will be written.",
    )
    run_parser.add_argument(
        "-s",
        "--skip-download",
        action="store_true",
        help="Skip downloading cited references from remote resolvers.",
    )
    run_parser.add_argument(
        "-n",
        "--max-references",
        type=int,
        default=None,
        help="Testing helper: process only the first N parsed references and their linked checks.",
    )

    return parser


def _handle_event(event: PipelineEvent) -> None:
    payload = event.payload
    if event.event == "stage_started":
        print(f"[AutoCheck] Starting {payload['stage']}...", flush=True)
        return

    if event.event == "stage_completed":
        if payload["stage"] == "extract":
            print(
                "[AutoCheck] Parsed "
                f"{payload['total_claims']} claims and {payload['total_references']} references.",
                flush=True,
            )
        elif payload["stage"] == "resolve_references":
            print(
                "[AutoCheck] Reference resolution completed: "
                f"resolved={payload['resolved']} "
                f"not_found={payload['not_found']} "
                f"skipped={payload['skipped']}.",
                flush=True,
            )
        elif payload["stage"] == "verify":
            summary = payload["summary"]
            print(
                "[AutoCheck] Verification completed: "
                f"strong={summary['strong_support']} "
                f"partial={summary['partial_support']} "
                f"unsupported={summary['unsupported_or_misleading']} "
                f"not_found={summary['not_found']}.",
                flush=True,
            )
        return

    if event.event == "reference_processed":
        record = payload["record"]
        print(
            "[AutoCheck] "
            f"[refs {payload['current']}/{payload['total']}] "
            f"{record['ref_id']} -> {record['status']}",
            flush=True,
        )
        return

    if event.event == "assessment_ready":
        assessment = payload["assessment"]
        print(
            "[AutoCheck] "
            f"[verify {payload['current']}/{payload['total']}] "
            f"{assessment['claim_id']} x {assessment['citation_marker']} "
            f"-> {assessment['verdict']}",
            flush=True,
        )
        return

    if event.event == "report_completed":
        print("[AutoCheck] Writing reports completed.", flush=True)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        settings = AppSettings.from_env(project_root=Path.cwd())
        pipeline = AutoCheckPipeline(settings)
        final_event: PipelineEvent | None = None
        for event in pipeline.run_incremental(
            source_path=args.source,
            report_dir=args.report_dir,
            skip_download=args.skip_download,
            max_references=args.max_references,
        ):
            _handle_event(event)
            if event.event == "report_completed":
                final_event = event

        if final_event is None:
            raise RuntimeError("Pipeline completed without emitting a final report event.")
        summary = final_event.payload["summary"]
        paths = final_event.payload["report_paths"]
        print(f"Assessments: {summary['total_assessments']}")
        print(f"Strong support: {summary['strong_support']}")
        print(f"Partial support: {summary['partial_support']}")
        print(f"Unsupported or misleading: {summary['unsupported_or_misleading']}")
        print(f"Not found: {summary['not_found']}")
        print(f"JSON report: {paths['json']}")
        print(f"Markdown report: {paths['markdown']}")
        print(f"Events stream: {paths['events']}")
