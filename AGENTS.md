# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `src/autocheck/`. Key areas:
- `pipeline/`: orchestration and claim verification flow
- `extractors/`: claim and reference extraction from input documents
- `services/`: reference resolution, retrieval, report writing, source loading
- `resolvers/`: OpenAlex, arXiv, CrossRef, Sci-Hub, and title-based lookup
- `web/`: FastAPI app plus static frontend assets in `web/static/`
- `schemas/`: Pydantic models shared across the pipeline

Tests live in `tests/`. Use `tests/fixtures/` for sample inputs. Generated runtime data goes under `data/workspaces/<paper-name>/`.

## Build, Test, and Development Commands
- `uv sync --dev`: install runtime and test dependencies
- `uv run pytest`: run the full test suite
- `uv run pytest tests/test_pipeline_smoke.py`: run one test module
- `uv run pytest -k "metadata_only"`: run tests matching a keyword
- `uv run autocheck run tests/fixtures/sample_draft.txt -s -n 2`: run the CLI locally
- `uv run autocheck web --host 127.0.0.1 --port 8000`: start the web UI
- `uv run python tests/check_title_downloads.py testpaper.md`: bulk-check DOI lookup and download results for one-title-per-line inputs

## Coding Style & Naming Conventions
Target Python 3.9+ with 4-space indentation. Follow existing patterns:
- `snake_case` for functions, variables, and modules
- `PascalCase` for classes and Pydantic models
- explicit type hints on public functions
- concise docstrings only where behavior is not obvious

Prefer small, composable service methods over large mixed-responsibility functions. Keep prompts in `src/autocheck/prompts/templates.py`. Reuse `schemas/models.py` instead of introducing duplicate response shapes.

When updating download-failure handling, preserve the distinction between:
- full-text verification using retrieved paper evidence
- bibliography-based citation matching fallback when the cited source is unavailable

Fallback wording and prompts should stay aligned with the final report output in `pipeline/verifier.py`.

## Testing Guidelines
Use `pytest`. Name files `tests/test_<feature>.py` and test functions `test_<behavior>()`. Prefer isolated tests with `tmp_path` and `monkeypatch`; avoid real network calls unless a test is explicitly integration-oriented. For resolver or LLM-related changes, cover both success and fallback paths.

For title-based download checks, prefer `tests/check_title_downloads.py` over ad hoc one-off shell snippets when you need repeatable local verification.

If `tests/test_pipeline_smoke.py` fails during collection under Python 3.10 because of `datetime.UTC`, treat that as an environment compatibility issue and note it explicitly instead of attributing it to unrelated resolver or prompt changes.

## Commit & Pull Request Guidelines
Recent history favors short imperative commits, often with prefixes like `feat:` and `chore:`. Use that style when possible, for example: `feat: add metadata-only citation fallback`.

PRs should include:
- a short problem/solution summary
- affected commands or endpoints
- test evidence, e.g. `uv run pytest tests/test_pipeline_smoke.py`
- screenshots only for web UI changes

## Configuration & Safety
Configuration is environment-driven via `AUTOCHECK_*` variables and `OPENAI_API_KEY`. Keep secrets out of Git. Default tests should work without network by using mocks and `skip_download=True`.
