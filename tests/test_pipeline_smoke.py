from pathlib import Path
import json

from autocheck.config.settings import AppSettings
from autocheck.pipeline.orchestrator import AutoCheckPipeline
from autocheck.schemas.models import VerificationLabel
from autocheck.utils.citations import match_citation_to_reference
from autocheck.schemas.models import ReferenceEntry


def test_pipeline_smoke_run_without_network(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
            "References\n"
            "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    report, paths = pipeline.run(source_path=source_path, skip_download=True)

    assert report.summary.total_claims == 1
    assert report.summary.total_assessments == 1
    assert report.assessments[0].verdict == VerificationLabel.NOT_FOUND
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert paths["events"].exists()
    assert Path(paths["json"]).read_text(encoding="utf-8")


def test_pipeline_emits_incremental_events(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
            "References\n"
            "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    events = list(pipeline.run_incremental(source_path=source_path, skip_download=True))

    assert events[0].event == "stage_started"
    assert any(event.event == "reference_processed" for event in events)
    assert any(event.event == "assessment_ready" for event in events)
    assert events[-1].event == "report_completed"
    first_reference_processed = next(
        index for index, event in enumerate(events) if event.event == "reference_processed"
    )
    first_assessment_ready = next(
        index for index, event in enumerate(events) if event.event == "assessment_ready"
    )
    resolve_completed = next(
        index
        for index, event in enumerate(events)
        if event.event == "stage_completed" and event.payload["stage"] == "resolve_references"
    )
    assert first_reference_processed < first_assessment_ready < resolve_completed

    report, paths = pipeline.run(source_path=source_path, skip_download=True)
    event_lines = [
        json.loads(line)
        for line in Path(paths["events"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(event_lines) >= len(events)
    assert event_lines[-1]["event"] == "report_completed"
    assert report.summary.total_assessments == 1


def test_partial_report_is_written_before_completion(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
            "References\n"
            "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    report_path = project_root / "data" / "reports" / "draft.report.json"

    for event in pipeline.run_incremental(source_path=source_path, skip_download=True):
        if event.event == "assessment_ready":
            break

    assert report_path.exists()
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["status"] == "running"
    assert report_payload["progress"]["completed_assessments"] >= 1
    assert len(report_payload["assessments"]) >= 1


def test_pipeline_can_limit_processed_references(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Claim one is supported by the first source [1].\n"
            "Claim two is supported by the second source [2].\n\n"
            "References\n"
            "[1] Author A. First Paper. 2017.\n"
            "[2] Author B. Second Paper. 2018.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    report, _paths = pipeline.run(
        source_path=source_path,
        skip_download=True,
        max_references=1,
    )

    assert len(report.parsed_document.references) == 1
    assert report.parsed_document.references[0].ref_id == "[1]"
    assert len(report.assessments) == 1
    assert report.assessments[0].citation_marker == "[1]"
    assert report.progress is not None
    assert report.progress.total_references == 1
    assert report.progress.total_assessments == 1


def test_numeric_citation_matching_is_exact() -> None:
    references = [
        ReferenceEntry(ref_id="[1]", raw_text="[1] First ref", aliases=["[1]"]),
        ReferenceEntry(ref_id="[13]", raw_text="[13] Thirteenth ref", aliases=["[13]"]),
    ]

    assert match_citation_to_reference("[13]", references).ref_id == "[13]"
    assert match_citation_to_reference("[3]", references) is None


def test_settings_default_to_llm_verification_only(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AUTOCHECK_ENABLE_LLM_EXTRACTION", raising=False)
    monkeypatch.delenv("AUTOCHECK_ENABLE_LLM_VERIFICATION", raising=False)
    monkeypatch.delenv("AUTOCHECK_CHAT_MODEL", raising=False)
    monkeypatch.delenv("AUTOCHECK_VERIFY_MODEL", raising=False)

    settings = AppSettings.from_env(project_root=tmp_path)
    assert settings.enable_llm_extraction is False
    assert settings.enable_llm_verification is True
    assert settings.chat_model == "gpt-5.4"
    assert settings.verify_model == "gpt-5.4"
