from pathlib import Path

from autocheck.config.settings import AppSettings, PaperWorkspace
from autocheck.services.source_resolver import (
    download_remote_source_to_workspace,
    is_http_url,
    normalize_remote_source_url,
    resolve_source_input,
    source_stem,
)


def test_is_http_url_detects_web_links() -> None:
    assert is_http_url("https://example.com/paper.pdf") is True
    assert is_http_url("http://example.com/paper.pdf") is True
    assert is_http_url("tests/fixtures/sample_draft.txt") is False
    assert is_http_url(Path("tests/fixtures/sample_draft.txt")) is False


def test_normalize_remote_source_url_maps_arxiv_abs_to_pdf() -> None:
    assert (
        normalize_remote_source_url("https://arxiv.org/abs/1706.03762")
        == "https://arxiv.org/pdf/1706.03762.pdf"
    )


def test_source_stem_uses_url_path() -> None:
    assert source_stem("https://arxiv.org/pdf/1706.03762.pdf") == "1706.03762"


def test_workspace_for_source_preserves_full_remote_identifier(tmp_path) -> None:
    settings = AppSettings.from_env(project_root=tmp_path)

    workspace = settings.workspace_for_source("https://arxiv.org/abs/1706.03762")

    assert workspace.root_dir == tmp_path / "data" / "workspaces" / "1706-03762"


def test_download_remote_source_to_workspace_uses_response_url_and_suffix(monkeypatch, tmp_path) -> None:
    workspace = PaperWorkspace(
        name="paper",
        root_dir=tmp_path / "paper",
        inputs_dir=tmp_path / "paper" / "inputs",
        downloads_dir=tmp_path / "paper" / "downloads",
        processed_dir=tmp_path / "paper" / "processed",
        reports_dir=tmp_path / "paper" / "reports",
    )

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        url = "https://example.com/files/paper.pdf"
        content = b"%PDF-1.4 demo"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "autocheck.services.source_resolver.requests.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    path = download_remote_source_to_workspace(
        "https://example.com/paper",
        workspace,
        timeout=5,
    )

    assert path.exists()
    assert path.suffix == ".pdf"
    assert path.read_bytes() == b"%PDF-1.4 demo"
    assert path.name == "paper.pdf"


def test_download_remote_source_to_workspace_keeps_name_from_input_url(monkeypatch, tmp_path) -> None:
    workspace = PaperWorkspace(
        name="attention-is-all-you-need",
        root_dir=tmp_path / "paper",
        inputs_dir=tmp_path / "paper" / "inputs",
        downloads_dir=tmp_path / "paper" / "downloads",
        processed_dir=tmp_path / "paper" / "processed",
        reports_dir=tmp_path / "paper" / "reports",
    )

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        url = "https://cdn.example.com/files/download.pdf?token=demo"
        content = b"%PDF-1.4 demo"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "autocheck.services.source_resolver.requests.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    path = download_remote_source_to_workspace(
        "https://example.com/papers/attention-is-all-you-need",
        workspace,
        timeout=5,
    )

    assert path.exists()
    assert path.name == "attention-is-all-you-need.pdf"


def test_resolve_source_input_returns_local_path_unchanged(tmp_path) -> None:
    workspace = PaperWorkspace(
        name="paper",
        root_dir=tmp_path / "paper",
        inputs_dir=tmp_path / "paper" / "inputs",
        downloads_dir=tmp_path / "paper" / "downloads",
        processed_dir=tmp_path / "paper" / "processed",
        reports_dir=tmp_path / "paper" / "reports",
    )
    source_path = tmp_path / "draft.txt"
    source_path.write_text("demo", encoding="utf-8")

    resolved = resolve_source_input(source_path, workspace)

    assert resolved == source_path
