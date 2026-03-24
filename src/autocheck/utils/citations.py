from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from autocheck.schemas.models import ReferenceEntry
from autocheck.utils.text import dedupe_preserve_order, normalize_whitespace


NUMERIC_CITATION_RE = re.compile(r"\[(?P<body>[0-9,\-\s]+)\]")
AUTHOR_YEAR_CITATION_RE = re.compile(
    r"\((?P<body>(?:[A-Z][A-Za-z'`\-]*[a-z][A-Za-z'`\-]*(?:\s+et al\.)?,?\s+\d{4}[a-z]?(?:\s*;\s*)?)+)\)"
)
REFERENCE_HEADING_RE = re.compile(
    r"\n(?P<header>references|bibliography|参考文献)\s*\n",
    flags=re.IGNORECASE,
)


def split_references_section(text: str) -> Tuple[str, str]:
    match = REFERENCE_HEADING_RE.search(text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), text[match.end() :].strip()


def extract_citation_markers(sentence: str) -> List[str]:
    markers: List[str] = []

    for match in NUMERIC_CITATION_RE.finditer(sentence):
        body = match.group("body")
        chunks = [piece.strip() for piece in body.split(",") if piece.strip()]
        for chunk in chunks:
            if "-" in chunk:
                start_str, end_str = [item.strip() for item in chunk.split("-", 1)]
                if start_str.isdigit() and end_str.isdigit():
                    start, end = int(start_str), int(end_str)
                    step = 1 if start <= end else -1
                    for value in range(start, end + step, step):
                        markers.append(f"[{value}]")
                else:
                    markers.append(f"[{chunk}]")
            else:
                markers.append(f"[{chunk}]")

    for match in AUTHOR_YEAR_CITATION_RE.finditer(sentence):
        body = match.group("body")
        parts = [piece.strip() for piece in body.split(";") if piece.strip()]
        for part in parts:
            markers.append(part)

    return dedupe_preserve_order(markers)


def extract_cited_sentences(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?。])\s+", normalize_whitespace(text))
    results = []
    for sentence in sentences:
        if NUMERIC_CITATION_RE.search(sentence) or AUTHOR_YEAR_CITATION_RE.search(sentence):
            results.append(sentence.strip())
    return dedupe_preserve_order(results)


def split_reference_entries(reference_text: str) -> List[str]:
    reference_text = reference_text.strip()
    if not reference_text:
        return []

    numeric_lines = re.split(r"\n(?=(?:\[\d+\]|\d+\.\s+))", reference_text)
    cleaned_numeric = [normalize_whitespace(line) for line in numeric_lines if normalize_whitespace(line)]
    if len(cleaned_numeric) > 1:
        return cleaned_numeric

    lines = [line.strip() for line in reference_text.splitlines() if line.strip()]
    entries: List[str] = []
    buffer: List[str] = []
    for line in lines:
        starts_new = bool(re.match(r"^(?:\[\d+\]|\d+\.\s+)", line))
        if starts_new and buffer:
            entries.append(normalize_whitespace(" ".join(buffer)))
            buffer = [line]
        else:
            buffer.append(line)
    if buffer:
        entries.append(normalize_whitespace(" ".join(buffer)))

    if len(entries) <= 1 and len(lines) > 1:
        yearish_lines = [line for line in lines if re.search(r"\b(?:19|20)\d{2}\b", line)]
        if len(yearish_lines) >= max(2, len(lines) // 2):
            return [normalize_whitespace(line) for line in lines]

    return entries if entries else [normalize_whitespace(reference_text)]


def build_reference_aliases(reference: ReferenceEntry) -> List[str]:
    aliases = list(reference.aliases)
    aliases.append(reference.ref_id)

    if reference.title:
        aliases.append(reference.title)

    if reference.authors and reference.year:
        first_author = _surname(reference.authors[0])
        aliases.append(f"{first_author} {reference.year}")
        aliases.append(f"{first_author}, {reference.year}")
        aliases.append(f"{first_author} et al. {reference.year}")

    aliases.extend(_extract_numeric_labels(reference.raw_text))
    return dedupe_preserve_order([normalize_alias(alias) for alias in aliases if alias])


def normalize_alias(alias: str) -> str:
    alias = alias.strip()
    alias = re.sub(r"[(),.]", " ", alias)
    alias = re.sub(r"\s+", " ", alias)
    return alias.lower()


def match_citation_to_reference(
    citation_marker: str,
    references: Iterable[ReferenceEntry],
) -> Optional[ReferenceEntry]:
    normalized_marker = normalize_alias(citation_marker)
    is_numeric_marker = bool(re.fullmatch(r"\[?\d+\]?", normalized_marker))
    for reference in references:
        aliases = build_reference_aliases(reference)
        if normalized_marker in aliases:
            return reference

    if is_numeric_marker:
        return None

    for reference in references:
        aliases = build_reference_aliases(reference)
        if any(normalized_marker in alias or alias in normalized_marker for alias in aliases):
            return reference

    return None


def _extract_numeric_labels(text: str) -> List[str]:
    labels = []
    label_match = re.match(r"^(?:\[(\d+)\]|(\d+)\.)", text.strip())
    if not label_match:
        return labels
    value = label_match.group(1) or label_match.group(2)
    labels.append(f"[{value}]")
    labels.append(value)
    return labels


def _surname(author: str) -> str:
    parts = [part.strip(",.") for part in author.split() if part.strip(",.")]
    return parts[-1] if parts else author
