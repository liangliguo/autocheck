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
        # 过滤掉数学公式中的伪引用（如 x ∈ [0, 1]）
        if not _is_likely_citation_context(sentence, match.start(), match.end()):
            continue
            
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
        # 检查是否包含真正的引用（排除数学符号）
        has_numeric_citation = False
        for match in NUMERIC_CITATION_RE.finditer(sentence):
            if _is_likely_citation_context(sentence, match.start(), match.end()):
                has_numeric_citation = True
                break
        
        if has_numeric_citation or AUTHOR_YEAR_CITATION_RE.search(sentence):
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


def _is_likely_citation_context(text: str, match_start: int, match_end: int) -> bool:
    """
    判断一个数字括号匹配是否更可能是文献引用而不是数学符号。
    
    通过分析前后文的特征来区分真实引用和数学表达式中的符号（如区间 [0, 1]）。
    
    Args:
        text: 完整文本
        match_start: 匹配的起始位置
        match_end: 匹配的结束位置
        
    Returns:
        True 表示更可能是引用，False 表示更可能是数学符号
    """
    context_before = text[max(0, match_start - 25):match_start]
    context_after = text[match_end:min(len(text), match_end + 15)]
    matched_text = text[match_start:match_end]
    
    # 提取匹配中的所有数字
    numbers = [int(n.strip()) for n in re.findall(r"\d+", matched_text)]
    
    # 规则1: 前面紧跟数学符号（强排除信号）
    # 如: x ∈ [0, 1], r + s ∈ [0, 100]
    math_symbols_before = r"[∈∉⊂⊆⊃⊇∩∪×·+\-*/=<>≤≥≈∝～]"
    if re.search(math_symbols_before + r"\s*$", context_before):
        return False
    
    # 规则2: 前面紧跟数学相关关键词（强排除信号）
    # 如: range [0, 1], interval [0, 100]
    math_keywords = r"(?:range|interval|from|between|within)\s*$"
    if re.search(math_keywords, context_before, re.IGNORECASE):
        return False
    
    # 规则3: 检查 "变量名 in/within/at [...]" 模式（排除），但保留 "shown in [...]" 引用模式
    # 如: value in [0, 1] (排除), as shown in [5] (保留)
    if re.search(
        r"(?:value|values|variable|variables|number|numbers|element|elements|probability|probabilities|parameter|parameters)\s+(?:in|within|at)\s*$",
        context_before,
        re.IGNORECASE,
    ):
        return False
    
    # 规则3.5: 检查中文 "值/参数/变量在 [...]" 或 "在...范围/区间 [...]" 模式
    if re.search(r"(?:值|参数|变量|概率|数值)在\s*$", context_before):
        return False
    if re.search(r"(?:在|的)(?:范围|区间)\s*$", context_before):
        return False
    
    # 规则4: [0, 1] 这种特殊模式的额外检查
    if len(numbers) == 2 and numbers[0] == 0 and numbers[1] == 1:
        # [0,1]后跟字母或幂次符号（如 [0,1]m, [0,1]^d）必定是数学表达式
        if re.match(r"^[a-zA-Z^]", context_after):
            return False
        # 如果没有明确的引用上下文标志，倾向认为是数学区间
        if not re.match(r"^[\s.,;。，；)\]]", context_after):
            return False
    
    # 规则5: 句子末尾或后跟标点符号（强引用信号）
    # 如: claim [1]. 或 work [5],
    if re.match(r"^[\s.,;:。，；：）\]\n]", context_after) or context_after.strip() == "":
        return True
    
    # 规则6: 数字较大（>20）通常是引用而非数学区间
    if numbers and max(numbers) > 20:
        return True
    
    # 规则7: 包含多个不连续的数字（如 [1, 5, 9]）更可能是引用列表
    if len(numbers) >= 3:
        is_sequential = all(numbers[i] + 1 == numbers[i + 1] for i in range(len(numbers) - 1))
        # 不连续或超长序列倾向于引用
        if not is_sequential or len(numbers) > 5:
            return True
    
    # 规则8: 前面有典型的引用引导词（强引用信号）
    # 如: as shown in [5], according to [10], see [3]
    citation_keywords = r"(?:shown in|reported in|described in|according to|see|cf\.|ref\.|reference|references|citation)\s*$"
    if re.search(citation_keywords, context_before, re.IGNORECASE):
        return True
    
    # 规则9: 单个较大的数字（>5）通常是引用
    if len(numbers) == 1 and numbers[0] > 5:
        return True
    
    # 规则10: 对于很小的数字（<=3）且没有明确引用标志，倾向于非引用
    if numbers and all(n <= 3 for n in numbers):
        return False
    
    # 默认：其他情况倾向于识别为引用
    return True
