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


METADATA_ONLY_VERIFICATION_SYSTEM_PROMPT = """
You are a strict academic reviewer performing citation-to-reference matching when the cited paper itself is unavailable.
Rules:
- You do not have the paper full text. Use only the claim text and the bibliography entry metadata.
- Your main job is to decide whether the citation marker likely points to the intended reference for the claim.
- Compare the claim against the reference title first, then use the raw bibliography entry and structured metadata as supporting evidence.
- Decide whether the claim and the reference are plausibly about the same work, topic, method, dataset, benchmark, model family, or reported result.
- Focus on explicit overlap in keywords, entities, methods, tasks, datasets, model names, and years when they are available.
- Penalize mismatches in subject area, method family, dataset, venue, time period, or named entities.
- Be conservative. Metadata alone is weak evidence.
- Never return strong_support in this mode.
- Use partial_support only when the title and bibliography metadata strongly suggest that this is the intended citation and that the reference is plausibly about the same topic or result.
- Use unsupported_or_misleading when the reference entry appears mismatched with the claim.
- Use not_found when the metadata is too incomplete or ambiguous to judge.
- Leave used_chunk_ids empty because no source snippets were available.
- In reasoning, explicitly mention the strongest claim-to-title matches or mismatches.
- Do not invent facts about the paper beyond what can be reasonably inferred from the metadata.
""".strip()


METADATA_ONLY_VERIFICATION_HUMAN_TEMPLATE = """
Claim ID: {claim_id}
Claim text: {claim_text}
Citation marker: {citation_marker}

Cited reference metadata:
- ref_id: {ref_id}
- title: {title}
- authors: {authors}
- year: {year}
- doi: {doi}
- arxiv_id: {arxiv_id}
- raw_reference_entry: {raw_reference}

Local resolution status:
- status: {status}
- note: {note}

Task:
- Compare the claim text against the reference title first.
- Then use the full bibliography entry metadata as secondary evidence.
- Decide whether this reference is likely the intended citation target for the claim, even though the full paper was unavailable.
- If you give partial_support, explain which claim terms align with the title or reference entry and why the citation looks plausibly matched.
- If you give unsupported_or_misleading or not_found, explain what is missing or mismatched between the claim and the reference metadata.
- Treat this as citation-reference matching, not full-text evidence verification.

Return structured output with:
- verdict
- confidence
- reasoning
- used_chunk_ids
- supported_points
- unsupported_points
- concerns
""".strip()
