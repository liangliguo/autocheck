from pathlib import Path
import json

from autocheck.config.settings import AppSettings
from autocheck.pipeline.orchestrator import AutoCheckPipeline
from autocheck.schemas.models import VerificationLabel


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
