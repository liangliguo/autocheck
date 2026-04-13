from __future__ import annotations

import re
import subprocess
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SCIHUB_MIRRORS = [
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
    "https://sci-hub.ren",
]


def normalize_doi(doi: str | None) -> Optional[str]:
    """Extract a canonical DOI string from common input formats."""
    if not doi:
        return None

    normalized = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if normalized.lower().startswith(prefix.lower()):
            normalized = normalized[len(prefix):]

    normalized = normalized.strip()
    return normalized if normalized.startswith("10.") else None


def normalize_mirror_url(url: str) -> str:
    """Normalize mirror URLs so deduplication works reliably."""
    return url.strip().rstrip("/")


def build_scihub_mirror_list(
    custom_url: str = "",
    mirrors: list[str] | None = None,
) -> list[str]:
    """Build a deduplicated Sci-Hub mirror list with an optional custom mirror first."""
    ordered: list[str] = []
    seen: set[str] = set()

    for candidate in ([custom_url] if custom_url else []) + list(mirrors or SCIHUB_MIRRORS):
        normalized = normalize_mirror_url(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)

    return ordered


def curl_get(url: str, timeout: int = 60, referer: str | None = None) -> tuple[int, bytes]:
    """Use curl to fetch URL content with browser-like headers."""
    command = [
        "curl",
        "-sL",
        "-A",
        USER_AGENT,
        "--connect-timeout",
        str(timeout),
        "-w",
        "\n%{http_code}",
    ]
    if referer:
        command.extend(["-e", referer])
    command.append(url)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout + 10,
            check=False,
        )
        output = result.stdout
        lines = output.rsplit(b"\n", 1)
        if len(lines) == 2:
            content, code_bytes = lines
            try:
                status_code = int(code_bytes)
            except ValueError:
                status_code = 0
                content = output
        else:
            content = output
            status_code = 200 if result.returncode == 0 else 0
        return status_code, content
    except subprocess.TimeoutExpired:
        return 0, b""
    except Exception:
        return 0, b""


def normalize_pdf_url(pdf_url: str, base_url: str) -> Optional[str]:
    """Convert relative or protocol-relative Sci-Hub PDF URLs to absolute URLs."""
    normalized = pdf_url.strip().replace("\\/", "/")
    if not normalized:
        return None

    normalized = normalized.split("#", 1)[0]
    if not normalized:
        return None

    if normalized.startswith("//"):
        return "https:" + normalized
    if normalized.startswith(("http://", "https://")):
        return normalized
    return urljoin(base_url.rstrip("/") + "/", normalized)


def extract_scihub_pdf_url(html: bytes, mirror: str) -> Optional[str]:
    """Extract the embedded PDF URL from a Sci-Hub landing page."""
    base_url = normalize_mirror_url(mirror)
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        soup = None

    candidates: list[str] = []

    if soup is not None:
        selectors = (
            ("embed", "src", {"type": "application/pdf"}),
            ("iframe", "src", {"id": "pdf"}),
            ("object", "data", {}),
            ("iframe", "src", {}),
            ("embed", "src", {}),
            ("a", "href", {}),
        )
        for tag_name, attr, attrs in selectors:
            for tag in soup.find_all(tag_name, attrs=attrs):
                value = tag.get(attr)
                if value:
                    candidates.append(value)

        for button in soup.find_all(attrs={"onclick": True}):
            candidates.append(button.get("onclick", ""))

    text = html.decode("utf-8", errors="ignore")
    for pattern in (
        r"location\.href\s*=\s*['\"]([^'\"]+)['\"]",
        r"""(?:src|href|data)\s*=\s*['"]([^'"]+)['"]""",
    ):
        candidates.extend(match.group(1) for match in re.finditer(pattern, text, re.IGNORECASE))

    for candidate in candidates:
        match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", candidate)
        raw_url = match.group(1) if match else candidate
        normalized = normalize_pdf_url(raw_url, base_url)
        if not normalized:
            continue

        lowered = normalized.lower()
        if any(token in lowered for token in (".pdf", "/pdf/", "/downloads/", "/tree/", "/uptodate/")):
            return normalized

    return None


def is_pdf_bytes(content: bytes) -> bool:
    """Check whether downloaded bytes look like a PDF payload."""
    return bool(content) and content.lstrip().startswith(b"%PDF")


def download_pdf_bytes(url: str, timeout: int = 120, referer: str | None = None) -> Optional[bytes]:
    """Download a PDF and validate the returned payload."""
    status, content = curl_get(url, timeout=timeout, referer=referer)
    if status != 200 or not is_pdf_bytes(content):
        return None
    return content
