from __future__ import annotations

import argparse
from pathlib import Path

from autocheck.config.settings import AppSettings
from autocheck.pipeline.orchestrator import AutoCheckPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocheck",
        description="Verify whether paper claims are supported by their cited references.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full verification pipeline.")
    run_parser.add_argument("source", help="Path to the PDF or text manuscript.")
    run_parser.add_argument(
        "--report-dir",
        default=None,
        help="Directory where JSON and Markdown reports will be written.",
    )
    run_parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloading cited references from remote resolvers.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        source_path = Path(args.source)
        settings = AppSettings.from_env(project_root=Path.cwd())
        pipeline = AutoCheckPipeline(settings)
        report, paths = pipeline.run(
            source_path=source_path,
            report_dir=args.report_dir,
            skip_download=args.skip_download,
        )
        print(f"Assessments: {report.summary.total_assessments}")
        print(f"Strong support: {report.summary.strong_support}")
        print(f"Partial support: {report.summary.partial_support}")
        print(f"Unsupported or misleading: {report.summary.unsupported_or_misleading}")
        print(f"Not found: {report.summary.not_found}")
        print(f"JSON report: {paths['json']}")
        print(f"Markdown report: {paths['markdown']}")
