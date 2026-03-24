from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from autocheck.schemas.models import LocalPaperRecord, ReferenceEntry, ResolverMatch
from autocheck.utils.text import slugify


class PaperLibrary:
    def __init__(self, downloads_dir: Path, processed_dir: Path) -> None:
        self.downloads_dir = downloads_dir
        self.processed_dir = processed_dir
        self.index_path = processed_dir / "library_index.json"
        self._records: Dict[str, LocalPaperRecord] = self._load_index()

    def list_records(self) -> List[LocalPaperRecord]:
        return list(self._records.values())

    def get(self, reference: ReferenceEntry | str) -> Optional[LocalPaperRecord]:
        record = None
        if isinstance(reference, ReferenceEntry):
            record = self._records.get(self._record_key(reference))
            if record is None:
                record = self._find_legacy_record(reference)
        else:
            record = self._records.get(reference) or self._find_legacy_record(reference)
        if record and record.pdf_path and not Path(record.pdf_path).exists():
            record.pdf_path = None
        if record and record.text_path and not Path(record.text_path).exists():
            record.text_path = None
        return record

    def ensure_placeholder(
        self,
        reference: ReferenceEntry,
        status: str = "pending",
        note: str | None = None,
    ) -> LocalPaperRecord:
        existing = self.get(reference)
        if existing:
            existing.ref_id = reference.ref_id
            if note:
                existing.note = note
            if status:
                existing.status = status
            self._save_record(existing)
            return existing

        record = LocalPaperRecord(
            record_key=self._record_key(reference),
            ref_id=reference.ref_id,
            title=reference.title,
            status=status,
            note=note,
        )
        self._save_record(record)
        return record

    def save_download(
        self,
        reference: ReferenceEntry,
        match: ResolverMatch,
        pdf_bytes: bytes,
    ) -> LocalPaperRecord:
        stem = self._file_stem(reference, match.title)
        pdf_path = self.downloads_dir / f"{stem}.pdf"
        pdf_path.write_bytes(pdf_bytes)

        record = LocalPaperRecord(
            record_key=self._record_key(reference),
            ref_id=reference.ref_id,
            title=match.title or reference.title,
            pdf_path=str(pdf_path),
            source_url=match.pdf_url or match.landing_page_url,
            resolver_name=match.resolver_name,
            status="downloaded",
        )
        self._save_record(record)
        return record

    def save_text(self, reference: ReferenceEntry, text: str) -> LocalPaperRecord:
        record = self.get(reference) or self.ensure_placeholder(reference)
        stem = self._file_stem(reference, record.title)
        text_path = self.processed_dir / f"{stem}.txt"
        text_path.write_text(text, encoding="utf-8")

        record.ref_id = reference.ref_id
        record.text_path = str(text_path)
        if record.status in {"pending", "downloaded", "cached"}:
            record.status = "processed"
        self._save_record(record)
        return record

    def mark_failure(self, reference: ReferenceEntry, status: str, note: str) -> LocalPaperRecord:
        record = self.get(reference) or self.ensure_placeholder(reference)
        record.ref_id = reference.ref_id
        record.status = status
        record.note = note
        self._save_record(record)
        return record

    def _load_index(self) -> Dict[str, LocalPaperRecord]:
        if not self.index_path.exists():
            return {}
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        records: Dict[str, LocalPaperRecord] = {}
        for key, data in payload.items():
            record = LocalPaperRecord.model_validate(data)
            record.record_key = record.record_key or key
            records[record.record_key] = record
        return records

    def _save_record(self, record: LocalPaperRecord) -> None:
        record.record_key = record.record_key or record.ref_id
        self._records[record.record_key] = record
        serializable = {key: value.model_dump() for key, value in self._records.items()}
        self.index_path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_legacy_record(self, reference: ReferenceEntry | str) -> Optional[LocalPaperRecord]:
        if isinstance(reference, str):
            ref_id = reference
            for record in self._records.values():
                if record.ref_id == ref_id:
                    return record
            return None

        for record in self._records.values():
            if record.ref_id != reference.ref_id:
                continue
            if reference.arxiv_id and record.source_url and reference.arxiv_id in record.source_url:
                return record
            if reference.title and record.title:
                if slugify(record.title) == slugify(reference.title):
                    return record
            if not reference.title and not reference.arxiv_id and not reference.doi:
                return record
        return None

    def _record_key(self, reference: ReferenceEntry) -> str:
        if reference.doi:
            return f"doi:{reference.doi.strip().lower()}"
        if reference.arxiv_id:
            return f"arxiv:{reference.arxiv_id.strip().lower()}"

        author_part = slugify(reference.authors[0], fallback="unknown") if reference.authors else "unknown"
        year_part = str(reference.year) if reference.year else "na"
        title_part = slugify(
            reference.title or reference.raw_text[:80],
            fallback="paper",
        )
        return f"title:{author_part}:{year_part}:{title_part}"

    def _file_stem(self, reference: ReferenceEntry, title: str | None) -> str:
        ref_part = slugify(reference.ref_id, fallback="ref")
        title_part = slugify(title or reference.title or reference.raw_text[:60], fallback="paper")
        return f"{ref_part}__{title_part}"
