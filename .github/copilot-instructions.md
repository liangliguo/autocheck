# Copilot Instructions for AutoCheck

AutoCheck is a LangChain-based tool that verifies whether citation-backed claims in academic papers are actually supported by the cited sources.

## Commands

```bash
# Install dependencies
uv sync --dev

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_pipeline_smoke.py

# Run a single test by name
uv run pytest -k "test_pipeline_smoke_run_without_network"

# Run CLI
uv run autocheck run <source> [options]

# Start web UI
uv run autocheck web --host 127.0.0.1 --port 8000
```

## Workflow

When making feature changes, run tests and commit automatically upon success:

```bash
uv run pytest && git add -A && git commit -m "<commit message>"
```

## Architecture

### Pipeline Flow

The verification pipeline (`AutoCheckPipeline`) processes papers through these stages:

1. **Extract** — `DocumentClaimReferenceExtractor` parses claims with citations and the reference list from the input document (PDF/TXT/MD)
2. **Resolve References** — `ReferenceManager` uses resolvers (OpenAlex → arXiv fallback) to find and download cited papers
3. **Verify** — `ClaimCitationVerifier` retrieves evidence chunks via `EvidenceRetriever` and uses LLM to assess each claim×citation pair
4. **Report** — `ReportWriter` outputs JSON, Markdown, and an incremental JSONL event stream

### Key Components

- **`AutoCheckPipeline`** (`pipeline/orchestrator.py`) — Main orchestrator; exposes `run()` (blocking) and `run_incremental()` (yields `PipelineEvent`s)
- **`AppSettings`** (`config/settings.py`) — Loads config from `.env`; creates per-paper `PaperWorkspace` directories
- **`PaperLibrary`** (`repository/library.py`) — Manages downloaded/processed reference papers
- **`EvidenceRetriever`** (`services/evidence_retriever.py`) — Chunks source texts and retrieves relevant passages using similarity search

### Data Models

All models are Pydantic classes in `schemas/models.py`:
- `ClaimRecord`, `ReferenceEntry` — Extracted from input paper
- `ClaimCitationAssessment` — Verification result with verdict, confidence, evidence
- `VerificationLabel` — Enum: `strong_support`, `partial_support`, `unsupported_or_misleading`, `not_found`
- `VerificationReport` — Final output containing parsed document, assessments, summary

### Workspace Structure

Each paper gets an isolated workspace under `data/workspaces/<paper-name>/`:
```
inputs/      # Local copy of input paper
downloads/   # Downloaded reference PDFs
processed/   # Extracted text from references
reports/     # Output JSON, Markdown, events
```

## Conventions

### Testing

- Tests use `tmp_path` fixture and `monkeypatch` to isolate from real config/network
- Mock LLM responses by creating a fake chat model that returns `LLMVerificationDecision` or `LLMClaimExtraction`
- Use `skip_download=True` to avoid network calls in unit tests

### Configuration

- All settings come from environment variables prefixed with `AUTOCHECK_`
- `enable_llm_extraction` defaults to `false`; `enable_llm_verification` defaults to `true`
- LLM models are built via `llm/factory.py` with support for OpenAI-compatible endpoints

### Citation Extraction

- Numeric citations like `[1]`, `[1, 2, 3]`, `[15-20]` are matched via regex in `utils/citations.py`
- Author-year citations like `(Smith et al., 2020)` are also supported
- Context analysis filters out false positives like math intervals `[0, 1]`
