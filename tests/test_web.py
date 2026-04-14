import json
from pathlib import Path

from fastapi.testclient import TestClient

from autocheck.config.settings import AppSettings
from autocheck.schemas.models import (
    ClaimCitationAssessment,
    ClaimRecord,
    EvidenceChunk,
    ParsedDocument,
    PipelineEvent,
    ReferenceEntry,
    ReportProgress,
    ReportSummary,
    VerificationLabel,
    VerificationReport,
)
from autocheck.web.app import create_app

_TEST_ENV_KEYS = (
    "OPENAI_API_KEY",
    "AUTOCHECK_OPENAI_BASE_URL",
    "AUTOCHECK_OPENAI_TIMEOUT",
    "AUTOCHECK_OPENAI_MAX_RETRIES",
    "AUTOCHECK_OPENAI_WIRE_API",
    "AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE",
    "AUTOCHECK_MODEL_REASONING_EFFORT",
    "AUTOCHECK_ENABLE_THINKING",
    "AUTOCHECK_THINKING_BUDGET",
    "AUTOCHECK_PRESERVE_THINKING",
    "AUTOCHECK_ENABLE_LLM_EXTRACTION",
    "AUTOCHECK_ENABLE_LLM_VERIFICATION",
    "AUTOCHECK_CHAT_MODEL",
    "AUTOCHECK_EXTRACT_MODEL",
    "AUTOCHECK_VERIFY_MODEL",
    "AUTOCHECK_TEMPERATURE",
    "AUTOCHECK_CHUNK_SIZE",
    "AUTOCHECK_CHUNK_OVERLAP",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
)


class FakePipeline:
    def __init__(self, _settings: AppSettings) -> None:
        self.settings = _settings
        self._current_run_paths = None

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
        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report, {
            "json": json_path,
            "markdown": markdown_path,
            "events": events_path,
        }

    def run_incremental(
        self,
        source_path,
        report_dir=None,
        workspace_dir=None,
        skip_download=False,
        max_references=None,
    ):
        report, paths = self.run(
            source_path=source_path,
            report_dir=report_dir,
            workspace_dir=workspace_dir,
            skip_download=skip_download,
            max_references=max_references,
        )
        self._current_run_paths = paths
        yield PipelineEvent(
            event="assessment_ready",
            timestamp="2026-03-24T00:00:00+00:00",
            payload={
                "stage": "verify",
                "current": 1,
                "total": 1,
                "assessment": report.assessments[0].model_dump(mode="json"),
            },
        )
        yield PipelineEvent(
            event="report_completed",
            timestamp="2026-03-24T00:00:01+00:00",
            payload={
                "stage": "write_report",
                "summary": report.summary.model_dump(mode="json"),
                "report_paths": {key: str(value) for key, value in paths.items()},
            },
        )


def _clear_env(monkeypatch) -> None:
    for key in _TEST_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_web_index_renders_frontend_shell(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "AutoCheck 论文引用核验系统" in response.text
    assert "论文引用核验系统" in response.text
    assert 'data-page="run"' in response.text
    assert "/assets/app.js" in response.text
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"


def test_web_config_page_renders_frontend_shell(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.get("/config")

    assert response.status_code == 200
    assert "系统配置管理" in response.text
    assert 'data-page="config"' in response.text
    assert "保存配置" in response.text


def test_api_run_accepts_pasted_text_and_returns_json(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.post(
        "/api/run",
        data={
            "manuscript_text": "Transformers use attention [1].\n\nReferences\n[1] Demo paper. 2017.",
            "max_references": "1",
            "skip_download": "on",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["summary"]["strong_support"] == 1
    assert payload["report_paths"]["markdown"].endswith("sample.report.md")
    assert payload["markdown_preview"] == "# Demo Report\n"
    assert "/data/workspaces/" in payload["source_path"]
    assert payload["recent_reports"][0].endswith("sample.report.json")


def test_api_run_stream_emits_incremental_updates(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/run/stream",
        data={
            "manuscript_text": "Transformers use attention [1].\n\nReferences\n[1] Demo paper. 2017.",
            "max_references": "1",
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["x-accel-buffering"] == "no"
        assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
        messages = [json.loads(line) for line in response.iter_lines() if line]

    assert any(message["event"] == "assessment_ready" for message in messages)
    assert messages[-1]["event"] == "report_completed"
    assert messages[-1]["run"]["report"]["summary"]["strong_support"] == 1


def test_api_run_rejects_missing_input(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.post("/api/run", data={})

    assert response.status_code == 400
    assert response.json()["detail"] == "请上传文件、填写论文链接，或在文本框里粘贴论文内容。"


def test_api_run_accepts_url_input_and_returns_json(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    downloaded = settings.workspaces_dir / "1706-03762" / "inputs" / "1706-03762.pdf"
    downloaded.parent.mkdir(parents=True, exist_ok=True)
    downloaded.write_bytes(b"%PDF-1.4 demo")

    monkeypatch.setattr(
        "autocheck.web.app.resolve_source_input",
        lambda *_args, **_kwargs: downloaded,
    )

    response = client.post(
        "/api/run",
        data={
            "manuscript_url": "https://arxiv.org/abs/1706.03762",
            "max_references": "1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_path"].endswith("1706-03762.pdf")
    assert payload["report"]["source_path"].endswith("1706-03762.pdf")


def test_api_run_rejects_multiple_input_modes(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.post(
        "/api/run",
        data={
            "manuscript_text": "demo",
            "manuscript_url": "https://arxiv.org/abs/1706.03762",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "请只选择一种输入方式：上传文件、填写论文链接，或粘贴文本。"


def test_api_recent_reports_are_collected_from_workspace_directories(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
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

    response = client.get("/api/reports/recent")

    assert response.status_code == 200
    assert response.json()["recent_reports"] == [str(report_path)]


def test_api_config_returns_effective_settings(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["env_path"] == str(tmp_path / ".env")
    assert payload["has_env_file"] is False
    assert payload["values"]["AUTOCHECK_VERIFY_MODEL"] == "qwen3-max"
    assert any(field["key"] == "OPENAI_API_KEY" for field in payload["fields"])


def test_api_config_updates_env_and_app_settings(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.put(
        "/api/config",
        json={
            "values": {
                "AUTOCHECK_VERIFY_MODEL": "gpt-5.4-mini",
                "AUTOCHECK_ENABLE_LLM_VERIFICATION": False,
                "AUTOCHECK_CHUNK_SIZE": 3200,
                "AUTOCHECK_CHUNK_OVERLAP": 400,
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["values"]["AUTOCHECK_VERIFY_MODEL"] == "gpt-5.4-mini"
    assert payload["values"]["AUTOCHECK_ENABLE_LLM_VERIFICATION"] is False
    assert client.app.state.settings.verify_model == "gpt-5.4-mini"
    assert client.app.state.settings.enable_llm_verification is False

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "AUTOCHECK_VERIFY_MODEL=gpt-5.4-mini" in env_text
    assert "AUTOCHECK_ENABLE_LLM_VERIFICATION=false" in env_text
    assert "AUTOCHECK_CHUNK_SIZE=3200" in env_text


def test_api_config_binds_thinking_to_json_mode(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.put(
        "/api/config",
        json={
            "values": {
                "AUTOCHECK_ENABLE_THINKING": True,
                "AUTOCHECK_STRUCTURED_OUTPUT_METHOD": "function_calling",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["values"]["AUTOCHECK_ENABLE_THINKING"] is True
    assert payload["values"]["AUTOCHECK_STRUCTURED_OUTPUT_METHOD"] == "json_mode"
    assert client.app.state.settings.structured_output_method == "json_mode"

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "AUTOCHECK_ENABLE_THINKING=true" in env_text
    assert "AUTOCHECK_STRUCTURED_OUTPUT_METHOD=json_mode" in env_text


def test_api_config_rejects_invalid_chunk_settings(tmp_path, monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = AppSettings.from_env(project_root=tmp_path)
    app = create_app(settings=settings, pipeline_factory=FakePipeline)
    client = TestClient(app)

    response = client.put(
        "/api/config",
        json={
            "values": {
                "AUTOCHECK_CHUNK_SIZE": 300,
                "AUTOCHECK_CHUNK_OVERLAP": 300,
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "切块重叠必须小于切块大小。"
