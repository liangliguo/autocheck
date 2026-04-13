from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


class DocumentLoader:
    def load_text(self, path: str | Path) -> str:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._load_pdf_text(file_path)
        return file_path.read_text(encoding="utf-8", errors="ignore")

    def _load_pdf_text(self, path: Path) -> str:
        reader = PdfReader(str(path), strict=False)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                return ""

        pages = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
                if not text.strip():
                    text = self._extract_page_text_with_layout(page)
            except Exception:
                continue
            pages.append(text)
        text = "\n\n".join(pages)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_page_text_with_layout(self, page) -> str:
        try:
            return page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            return ""
