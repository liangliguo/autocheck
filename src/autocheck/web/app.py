from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from autocheck.config.settings import AppSettings, PaperWorkspace
from autocheck.pipeline.orchestrator import AutoCheckPipeline
from autocheck.schemas.models import VerificationReport
from autocheck.services.source_resolver import resolve_source_input
from autocheck.web.configuration import ConfigResponse, ConfigSaveRequest, ConfigService

PipelineFactory = Callable[[AppSettings], AutoCheckPipeline]

_ALLOWED_INPUT_SUFFIXES = {".pdf", ".txt", ".md"}


class RecentReportsResponse(BaseModel):
    recent_reports: list[str]


class RunResponse(BaseModel):
    source_path: str
    report: VerificationReport
    report_paths: dict[str, str]
    markdown_preview: str
    recent_reports: list[str]


def create_app(
    settings: AppSettings | None = None,
    pipeline_factory: PipelineFactory = AutoCheckPipeline,
) -> FastAPI:
    resolved_settings = settings or AppSettings.from_env(project_root=Path.cwd())
    resolved_settings.ensure_directories()

    app = FastAPI(title="AutoCheck 论文引用核验系统")
    app.state.settings = resolved_settings
    app.state.pipeline_factory = pipeline_factory
    app.state.config_service = ConfigService(project_root=resolved_settings.project_root)

    static_dir = _static_dir()
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/", response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/config", response_class=FileResponse)
    def config_page() -> FileResponse:
        return FileResponse(static_dir / "config.html")

    @app.get("/api/reports/recent", response_model=RecentReportsResponse)
    def recent_reports(request: Request) -> RecentReportsResponse:
        settings = _settings_from_request(request)
        return RecentReportsResponse(recent_reports=_recent_reports(settings))

    @app.get("/api/config", response_model=ConfigResponse)
    def get_config(request: Request) -> ConfigResponse:
        settings = _settings_from_request(request)
        config_service = _config_service_from_request(request)
        return config_service.build_response(settings=settings)

    @app.put("/api/config", response_model=ConfigResponse)
    def update_config(
        payload: ConfigSaveRequest,
        request: Request,
    ) -> ConfigResponse:
        settings = _settings_from_request(request)
        config_service = _config_service_from_request(request)
        try:
            refreshed_settings, response = config_service.save(
                current_settings=settings,
                raw_values=payload.values,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.settings = refreshed_settings
        return response

    @app.post("/api/run", response_model=RunResponse)
    async def run(
        request: Request,
        manuscript_text: str = Form(default=""),
        manuscript_file: UploadFile | None = File(default=None),
        manuscript_url: str = Form(default=""),
        max_references: str = Form(default=""),
        report_dir: str = Form(default=""),
        skip_download: bool = Form(default=False),
    ) -> RunResponse:
        settings = _settings_from_request(request)
        try:
            source_path, workspace = await _prepare_source(
                settings=settings,
                manuscript_text=manuscript_text,
                manuscript_file=manuscript_file,
                manuscript_url=manuscript_url,
            )
            output_dir = _resolve_report_dir(settings, workspace, report_dir)
            pipeline_factory = request.app.state.pipeline_factory
            pipeline = pipeline_factory(settings)
            report, paths = pipeline.run(
                source_path=source_path,
                report_dir=output_dir,
                workspace_dir=workspace.root_dir,
                skip_download=skip_download,
                max_references=_parse_max_references(max_references),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
        return RunResponse(
            source_path=str(source_path),
            report=report,
            report_paths={key: str(value) for key, value in paths.items()},
            markdown_preview=markdown,
            recent_reports=_recent_reports(settings),
        )

    return app


def run_web_server(app: FastAPI, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


async def _prepare_source(
    settings: AppSettings,
    manuscript_text: str,
    manuscript_file: UploadFile | None,
    manuscript_url: str,
) -> tuple[Path, PaperWorkspace]:
    has_text = bool(manuscript_text.strip())
    has_file = bool(manuscript_file and manuscript_file.filename)
    has_url = bool(manuscript_url.strip())
    selected_count = sum((has_text, has_file, has_url))

    if selected_count > 1:
        raise ValueError("请只选择一种输入方式：上传文件、填写论文链接，或粘贴文本。")
    if selected_count == 0:
        raise ValueError("请上传文件、填写论文链接，或在文本框里粘贴论文内容。")

    if has_file and manuscript_file is not None:
        original_name = Path(manuscript_file.filename or "")
        suffix = original_name.suffix.lower()
        if suffix not in _ALLOWED_INPUT_SUFFIXES:
            raise ValueError("上传文件只支持 PDF、TXT 或 MD。")
        workspace = settings.workspace_for_source(original_name.name)
        workspace.ensure_directories()
        target_path = workspace.inputs_dir / _build_input_name(original_name.stem, suffix)
        target_path.write_bytes(await manuscript_file.read())
        return target_path, workspace

    if has_url:
        workspace = settings.workspace_for_source(manuscript_url.strip())
        workspace.ensure_directories()
        try:
            target_path = resolve_source_input(
                manuscript_url.strip(),
                workspace,
                timeout=settings.openai_timeout,
            )
        except requests.RequestException as exc:
            raise ValueError(f"下载论文链接失败：{exc}") from exc
        return target_path, workspace

    workspace = settings.workspace_for_source(
        f"pasted-manuscript-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    workspace.ensure_directories()
    target_path = workspace.inputs_dir / _build_input_name("pasted-manuscript", ".txt")
    target_path.write_text(manuscript_text, encoding="utf-8")
    return target_path, workspace


def _build_input_name(stem: str, suffix: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in stem).strip("-")
    safe_stem = safe_stem or "input"
    return f"{timestamp}-{safe_stem}-{uuid4().hex[:8]}{suffix}"


def _parse_max_references(raw_value: str) -> int | None:
    value = raw_value.strip()
    if not value:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("最大参考文献数量必须是正整数。")
    return parsed


def _resolve_report_dir(
    settings: AppSettings,
    workspace: PaperWorkspace,
    raw_value: str,
) -> Path:
    value = raw_value.strip()
    if not value:
        return workspace.reports_dir
    target = Path(value)
    if not target.is_absolute():
        target = settings.project_root / target
    target.mkdir(parents=True, exist_ok=True)
    return target


def _recent_reports(settings: AppSettings) -> list[str]:
    if not settings.workspaces_dir.exists():
        return []
    candidates = sorted(
        settings.workspaces_dir.glob("*/reports/*.report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [str(path) for path in candidates[:6]]


def _settings_from_request(request: Request) -> AppSettings:
    return request.app.state.settings


def _config_service_from_request(request: Request) -> ConfigService:
    return request.app.state.config_service


def _static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"
