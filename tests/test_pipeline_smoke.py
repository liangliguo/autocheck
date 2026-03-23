from pathlib import Path

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
    assert Path(paths["json"]).read_text(encoding="utf-8")
