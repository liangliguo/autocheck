from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from autocheck.services.source_resolver import source_stem
from autocheck.utils.text import slugify


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PaperWorkspace:
    name: str
    root_dir: Path
    inputs_dir: Path
    downloads_dir: Path
    processed_dir: Path
    reports_dir: Path

    def ensure_directories(self) -> None:
        for path in (
            self.root_dir,
            self.inputs_dir,
            self.downloads_dir,
            self.processed_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    data_dir: Path
    workspaces_dir: Path
    downloads_dir: Path
    processed_dir: Path
    reports_dir: Path
    chat_model: str
    extract_model: str
    verify_model: str
    temperature: float
    chunk_size: int
    chunk_overlap: int
    openai_api_key: str
    openai_base_url: str
    openai_timeout: float
    openai_max_retries: int
    openai_wire_api: str
    openai_disable_response_storage: bool
    model_reasoning_effort: str
    enable_llm_extraction: bool
    enable_llm_verification: bool

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "AppSettings":
        root = (project_root or Path.cwd()).resolve()
        load_dotenv(root / ".env", override=False)
        data_dir = root / "data"
        return cls(
            project_root=root,
            data_dir=data_dir,
            workspaces_dir=data_dir / "workspaces",
            downloads_dir=data_dir / "downloads",
            processed_dir=data_dir / "processed",
            reports_dir=data_dir / "reports",
            chat_model=os.getenv("AUTOCHECK_CHAT_MODEL", "gpt-5.4"),
            extract_model=os.getenv("AUTOCHECK_EXTRACT_MODEL", ""),
            verify_model=os.getenv("AUTOCHECK_VERIFY_MODEL", "gpt-5.4"),
            temperature=float(os.getenv("AUTOCHECK_TEMPERATURE", "0")),
            chunk_size=int(os.getenv("AUTOCHECK_CHUNK_SIZE", "2200")),
            chunk_overlap=int(os.getenv("AUTOCHECK_CHUNK_OVERLAP", "300")),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=(
                os.getenv("AUTOCHECK_OPENAI_BASE_URL")
                or os.getenv("OPENAI_BASE_URL")
                or os.getenv("OPENAI_API_BASE")
                or ""
            ),
            openai_timeout=float(os.getenv("AUTOCHECK_OPENAI_TIMEOUT", "120")),
            openai_max_retries=int(os.getenv("AUTOCHECK_OPENAI_MAX_RETRIES", "2")),
            openai_wire_api=os.getenv("AUTOCHECK_OPENAI_WIRE_API", "responses"),
            openai_disable_response_storage=_get_bool_env(
                "AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE",
                default=True,
            ),
            model_reasoning_effort=os.getenv("AUTOCHECK_MODEL_REASONING_EFFORT", ""),
            enable_llm_extraction=_get_bool_env(
                "AUTOCHECK_ENABLE_LLM_EXTRACTION",
                default=False,
            ),
            enable_llm_verification=_get_bool_env(
                "AUTOCHECK_ENABLE_LLM_VERIFICATION",
                default=True,
            ),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.workspaces_dir,
            self.downloads_dir,
            self.processed_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def workspace_name_for_source(self, source_path: str | Path) -> str:
        return slugify(source_stem(source_path), fallback="paper")

    def workspace_for_source(
        self,
        source_path: str | Path,
        workspace_dir: str | Path | None = None,
    ) -> PaperWorkspace:
        if workspace_dir is None:
            root_dir = self.workspaces_dir / self.workspace_name_for_source(source_path)
        else:
            root_dir = Path(workspace_dir)
            if not root_dir.is_absolute():
                root_dir = self.project_root / root_dir

        return PaperWorkspace(
            name=root_dir.name,
            root_dir=root_dir,
            inputs_dir=root_dir / "inputs",
            downloads_dir=root_dir / "downloads",
            processed_dir=root_dir / "processed",
            reports_dir=root_dir / "reports",
        )
