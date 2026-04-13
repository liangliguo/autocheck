from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

import requests

from autocheck.utils.text import slugify

if TYPE_CHECKING:
    from autocheck.config.settings import PaperWorkspace


_ALLOWED_SOURCE_SUFFIXES = {".pdf", ".txt", ".md"}
_CONTENT_TYPE_TO_SUFFIX = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/x-markdown": ".md",
}


def is_http_url(value: str | Path) -> bool:
    if isinstance(value, Path):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_remote_source_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.netloc == "arxiv.org" and parsed.path.startswith("/abs/"):
        identifier = parsed.path.removeprefix("/abs/").strip("/")
        return f"https://arxiv.org/pdf/{identifier}.pdf"
    return cleaned


def source_stem(value: str | Path) -> str:
    if isinstance(value, Path):
        return value.stem

    candidate = value.strip()
    if not is_http_url(candidate):
        return Path(candidate).stem

    normalized = normalize_remote_source_url(candidate)
    parsed = urlparse(normalized)
    stem = Path(unquote(parsed.path)).stem
    if stem:
        return stem
    if parsed.netloc:
        return parsed.netloc
    return "paper"


def resolve_source_input(
    source: str | Path,
    workspace: PaperWorkspace,
    timeout: float = 120,
) -> Path:
    if not is_http_url(source):
        return Path(source)
    return download_remote_source_to_workspace(str(source), workspace, timeout=timeout)


def download_remote_source_to_workspace(
    url: str,
    workspace: PaperWorkspace,
    timeout: float = 120,
) -> Path:
    workspace.ensure_directories()
    normalized_url = normalize_remote_source_url(url)
    response = requests.get(normalized_url, timeout=timeout)
    response.raise_for_status()

    suffix = _resolve_source_suffix(
        response.url or normalized_url,
        response.headers.get("content-type", ""),
    )
    # Keep a stable local filename based on the original user input instead of
    # a redirected CDN/download URL like `download.pdf`.
    stem = slugify(source_stem(url), fallback=workspace.name or "input")
    target_path = workspace.inputs_dir / f"{stem}{suffix}"
    target_path.write_bytes(response.content)
    return target_path


def _resolve_source_suffix(url: str, content_type: str) -> str:
    path_suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if path_suffix in _ALLOWED_SOURCE_SUFFIXES:
        return path_suffix

    mime_type = content_type.split(";", 1)[0].strip().lower()
    if mime_type in _CONTENT_TYPE_TO_SUFFIX:
        return _CONTENT_TYPE_TO_SUFFIX[mime_type]

    raise ValueError("论文链接只支持 PDF、TXT 或 MD 资源。")
