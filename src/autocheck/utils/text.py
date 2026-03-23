from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable, List


WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def slugify(value: str, fallback: str = "paper") -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or fallback


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])|(?<=。)\s*", normalize_whitespace(text))
    return [part.strip() for part in parts if part.strip()]


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


def lexical_overlap_score(query: str, document: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    doc_tokens = set(tokenize(document))
    overlap = len(query_tokens & doc_tokens)
    coverage = overlap / len(query_tokens)
    density = overlap / max(len(doc_tokens), 1)
    return round((coverage * 0.8) + (density * 0.2), 6)


def ensure_suffix(path: Path, suffix: str) -> Path:
    return path if path.suffix == suffix else path.with_suffix(suffix)


def dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
