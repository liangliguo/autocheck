from pathlib import Path

from fastapi.testclient import TestClient

from autocheck.config.settings import AppSettings
from autocheck.schemas.models import (
    ClaimCitationAssessment,
    ClaimRecord,
    EvidenceChunk,
    ParsedDocument,
    ReferenceEntry,
    ReportProgress,
    ReportSummary,
    VerificationLabel,
    VerificationReport,
)
from autocheck.web.app import create_app


class FakePipeline:
    def __init__(self, _settings: AppSettings) -> None:
        self.settings = _settings

    def run(
        self,
        source_path,
        report_dir=None,
        workspace_dir=None,
        skip_download=False,
        max_references=None,
    ):
        output_dir = Path(report_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "sample.report.md"
        json_path = output_dir / "sample.report.json"
        events_path = output_dir / "sample.events.jsonl"
        markdown_path.write_text("# Demo Report\n", encoding="utf-8")
        json_path.write_text("{}", encoding="utf-8")
        events_path.write_text("", encoding="utf-8")

        report = VerificationReport(
            source_path=str(source_path),
            generated_at="2026-03-24T00:00:00+00:00",
            status="completed",
            progress=ReportProgress(
                total_references=1,
                completed_references=1,
                total_assessments=1,
                completed_assessments=1,
            ),
            summary=ReportSummary(
                total_claims=1,
                total_assessments=1,
                strong_support=1,
                partial_support=0,
                unsupported_or_misleading=0,
                not_found=0,
            ),
            parsed_document=ParsedDocument(
                source_path=str(source_path),
                body_text="Body",
                references_text="References",
                claims=[
                    ClaimRecord(
                        claim_id="claim-1",
                        text="Transformers use attention [1].",
                        citation_markers=["[1]"],
                    )
                ],
                references=[
                    ReferenceEntry(
                        ref_id="[1]",
                        raw_text="[1] Attention is all you need.",
                        title="Attention is all you need",
                        authors=["Author A"],
                        year=2017,
                    )
                ],
            ),
            local_library=[],
            assessments=[
                ClaimCitationAssessment(
                    claim_id="claim-1",
                    claim_text="Transformers use attention [1].",
                    citation_marker="[1]",
                    reference=ReferenceEntry(
                        ref_id="[1]",
                        raw_text="[1] Attention is all you need.",
                        title="Attention is all you need",
                        authors=["Author A"],
                        year=2017,
                    ),
                    verdict=VerificationLabel.STRONG_SUPPORT,
                    confidence=0.95,
                    reasoning="The cited paper directly supports the claim.",
                    evidence=[
                        EvidenceChunk(
                            chunk_id="[1]#1",
                            ref_id="[1]",
                            source_title="Attention is all you need",
                            score=0.95,
                            text="Attention is introduced as the central mechanism.",
                        )
                    ],
                )
            ],
        )
        return report, {
            "json": json_path,
            "markdown": markdown_path,
            "events": events_path,
        }


def test_web_index_renders_form(tmp_path) -> None:
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "AutoCheck Studio" in response.text
    assert "运行 AutoCheck" in response.text


def test_web_run_accepts_pasted_text_and_renders_output(tmp_path) -> None:
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.post(
        "/run",
        data={
            "manuscript_text": "Transformers use attention [1].\n\nReferences\n[1] Demo paper. 2017.",
            "max_references": "1",
            "skip_download": "on",
        },
    )

    assert response.status_code == 200
    assert "结果面板" in response.text
    assert "strong_support" in response.text
    assert "sample.report.md" in response.text
    assert "data/workspaces" in response.text


def test_web_run_rejects_missing_input(tmp_path) -> None:
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.post("/run", data={})

    assert response.status_code == 200
    assert "请上传一个文件，或在文本框里粘贴论文内容。" in response.text


def test_web_recent_reports_are_collected_from_workspace_directories(tmp_path) -> None:
    settings = AppSettings.from_env(project_root=tmp_path)
    report_path = (
        settings.workspaces_dir
        / "demo-paper"
        / "reports"
        / "demo-paper.report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")

    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "demo-paper.report.json" in response.text
