# doc-creator

Agentic document generator: secure input handling and document conversion.

## Setup

- **Install:** `uv sync` (installs pydantic, pydantic-settings, pytest, pytest-cov). For dev tools: `uv sync --extra dev` (adds ruff, mypy).
- **Run tests:** `uv run pytest tests/ -v`
- **Coverage:** `uv run pytest tests/ --cov=backend --cov-report=term-missing`
- **Lint/format:** `uv run ruff check .` then `uv run ruff format .`
- **Type check:** `MYPYPATH=src uv run mypy -p backend`

## Story 1.1 – InputSanitizer

- **Location:** `src/backend/utils/sanitizer.py`
- **Config:** `SanitizerSettings` in `src/backend/utils/settings.py`; env prefix `INPUT_` (e.g. `INPUT_MAX_FILE_SIZE_BYTES`, `INPUT_ALLOWED_EXTENSIONS` as JSON array).
- **Validation order:** resolve path → under base_dir → exists → extension (blocklist then whitelist) → size via `stat()` only → UTF-8 check. Size is never determined by reading the file.
- **Security tests:** Tagged with `@pytest.mark.security` in `tests/test_sanitizer.py`.
