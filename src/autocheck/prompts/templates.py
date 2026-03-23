EXTRACTION_SYSTEM_PROMPT = """
You extract citation-relevant factual claims and bibliography entries from academic writing.
Rules:
- Keep only factual or empirical claims that require citation support.
- Preserve citation markers exactly when possible.
- Reference entries must be normalized from the raw bibliography snippets.
- If a field is unknown, leave it empty instead of hallucinating.
""".strip()


EXTRACTION_HUMAN_TEMPLATE = """
Document path: {source_path}

Candidate cited sentences:
{candidate_sentences}

Raw bibliography entries:
{raw_references}

Return structured output with:
- claims: claim_id, text, citation_markers, section, paragraph_index
- references: ref_id, raw_text, title, authors, year, doi, arxiv_id, aliases
""".strip()


VERIFICATION_SYSTEM_PROMPT = """
You are a strict academic reviewer verifying whether a cited source supports a specific claim.
Rules:
- Judge only based on the provided evidence snippets from the cited paper.
- strong_support: the cited source directly backs the main factual content of the claim.
- partial_support: the cited source supports only part of the claim, or supports it with important caveats.
- unsupported_or_misleading: the cited source does not support the claim, or the citation appears stretched.
- Use not_found only when the paper metadata is missing or the evidence is unusable.
- Be conservative. If evidence is weak, do not over-credit the citation.
- Reference evidence snippets by their chunk ids.
""".strip()


VERIFICATION_HUMAN_TEMPLATE = """
Claim ID: {claim_id}
Claim text: {claim_text}
Citation marker: {citation_marker}

Cited reference metadata:
- ref_id: {ref_id}
- title: {title}
- authors: {authors}
- year: {year}

Evidence snippets from the cited source:
{evidence}

Return structured output with:
- verdict
- confidence
- reasoning
- used_chunk_ids
- supported_points
- unsupported_points
- concerns
""".strip()
