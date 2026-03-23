from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from autocheck.schemas.models import VerificationReport


class ReportWriter:
    def write(
        self,
        report: VerificationReport,
        output_dir: str | Path,
        stem: str,
    ) -> Dict[str, Path]:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        json_path = target_dir / f"{stem}.report.json"
        markdown_path = target_dir / f"{stem}.report.md"

        json_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        markdown_path.write_text(self._render_markdown(report), encoding="utf-8")

        return {"json": json_path, "markdown": markdown_path}

    def _render_markdown(self, report: VerificationReport) -> str:
        summary = report.summary
        lines = [
            "# AutoCheck Verification Report",
            "",
            f"- Source: `{report.source_path}`",
            f"- Generated at: `{report.generated_at.isoformat()}`",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Total claims | {summary.total_claims} |",
            f"| Total assessments | {summary.total_assessments} |",
            f"| Strong support | {summary.strong_support} |",
            f"| Partial support | {summary.partial_support} |",
            f"| Unsupported or misleading | {summary.unsupported_or_misleading} |",
            f"| Not found | {summary.not_found} |",
            "",
            "## Assessments",
            "",
        ]

        for item in report.assessments:
            title = item.reference.title if item.reference and item.reference.title else "Unknown reference"
            lines.extend(
                [
                    f"### {item.claim_id} x {item.citation_marker}",
                    "",
                    f"- Verdict: `{item.verdict.value}`",
                    f"- Confidence: `{item.confidence:.2f}`",
                    f"- Claim: {item.claim_text}",
                    f"- Reference: {title}",
                    f"- Reasoning: {item.reasoning}",
                ]
            )

            if item.supported_points:
                lines.append(f"- Supported points: {'; '.join(item.supported_points)}")
            if item.unsupported_points:
                lines.append(f"- Unsupported points: {'; '.join(item.unsupported_points)}")
            if item.concerns:
                lines.append(f"- Concerns: {'; '.join(item.concerns)}")

            if item.evidence:
                evidence_text = " | ".join(
                    f"{chunk.chunk_id}: {chunk.text[:220].replace(chr(10), ' ')}"
                    for chunk in item.evidence
                )
                lines.append(f"- Evidence: {evidence_text}")

            lines.append("")

        return "\n".join(lines)
