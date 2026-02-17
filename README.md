# doc-creator

Agentic document generator: secure input handling and document conversion.

## Overview

`doc-creator` is an AI-powered document generation system that converts text-based files (`.txt`, `.log`, `.md`) into professionally formatted `.docx` documents. It uses LangGraph for workflow orchestration, LLM for intelligent content structuring, and docx-js for high-quality DOCX output.

## Features

- **Multi-format input**: Accept `.txt`, `.log`, `.md` files with UTF-8 validation
- **AI-driven structuring**: Organizes content into chapters, sections, and subsections
- **Self-healing**: Automatic error detection and correction with specialized handlers
- **Human-in-the-loop**: Pause and prompt for missing file resolution
- **Session isolation**: UUID-based directory structure for concurrent operations
- **Checkpointing**: Version snapshots after each chapter for rollback capability
- **Quality validation**: Pre-conversion markdownlint and post-generation quality checks

## Installation

```bash
# Install dependencies
uv sync

# Install dev dependencies (ruff, mypy)
uv sync --extra dev
```

## Quick Start

```python
from pathlib import Path
from backend.entry import generate_document

# Generate a document from markdown files
result = generate_document(
    requested_paths=["input/document.md"],
    base_dir=Path("./input"),
)

if result["success"]:
    print(f"Created: {result['output_path']}")
else:
    print(f"Error: {result.get('error')}")
```

## Architecture

For detailed architecture, see [ARCHITECTURE.md](./.project/ARCHITECTURE.md).

### High-Level Flow

```
Input Files → Validate → Session Create → Copy Inputs
                                          ↓
                    ┌─────────────────────┼─────────────────────┐
                    ↓                     ↓                     ↓
              Scan Assets           Agent Loop           Validation
              (find images)       (generate MD)        (markdownlint)
                    ↓                     ↓                     ↓
              Missing Refs         Checkpoint           Parse to JSON
              (human input)        (save version)       (structure.json)
                    ↓                                         ↓
                    └─────────────────────┬───────────────────┘
                                          ↓
                                    Convert to DOCX
                                    (docx-js Node.js)
                                          ↓
                                    Quality Check
                                          ↓
                                    Save Results
                                          ↓
                                    Cleanup (archive)
```

### Key Components

- **`backend/entry.py`**: Entry point - validate, create session, invoke workflow, cleanup
- **`backend/graph.py`**: LangGraph workflow definition with nodes and edges
- **`backend/graph_nodes.py`**: Individual node implementations (scan_assets, agent, validate_md, checkpoint, etc.)
- **`backend/state.py`**: DocumentState TypedDict for workflow state
- **`backend/utils/`:
  - `session_manager.py`: UUID-based session lifecycle
  - `sanitizer.py`: Path traversal and input validation
  - `checkpoint.py`: Version snapshot management
  - `quality_validator.py`: Output quality verification

## Epics Summary

### Epic 1: Core Infrastructure
- **Story 1.1**: InputSanitizer with path traversal prevention
- **Story 1.2**: SessionManager with UUID-based session directories
- **Story 1.3**: File discovery and validation
- **Story 1.4**: Entry point with session lifecycle

### Epic 2: Agent Loop & Validation
- **Story 2.1**: Basic agent loop with LLM invocation
- **Story 2.2**: Agent reads current document state before appending
- **Story 2.3**: Tool definitions (checkpoint, human_input, etc.)
- **Story 2.4**: Interrupt/resume for human decision handling
- **Story 2.5**: Validation and parsing nodes (validate_md, parse_to_json)

### Epic 3: Asset Handling
- **Story 3.1**: Image reference scanning and classification
- **Story 3.2**: Copy images to session assets and rewrite references
- **Story 3.3**: Placeholder insertion for missing references
- **Story 3.4**: Missing reference tracking by source file

### Epic 4: Checkpointing & Rollback
- **Story 4.1**: Checkpoint node creates timestamped snapshots
- **Story 4.2**: Rollback node restores from checkpoints
- **Story 4.3**: Validation fix loop with retry logic
- **Story 4.4**: Integration test for checkpoint/rollback flow

### Epic 5: Parse/Convert/Quality
- **Story 5.1**: parse_to_json converts markdown to structure.json
- **Story 5.2**: convert_with_docxjs_node calls Node.js converter
- **Story 5.3**: quality_check_node verifies DOCX output
- **Story 5.4**: save_results_node finalizes output
- **Story 5.5**: Error recovery in conversion flow

### Epic 6: Error Handling
- **Story 6.1**: Error classifier categorizes errors
- **Story 6.2**: Syntax handler fixes markdown issues
- **Story 6.3**: Encoding handler detects and fixes encoding
- **Story 6.4**: Structural handler fixes document structure
- **Story 6.5**: Asset handler fixes missing/broken assets

## API Reference

### `generate_document()`

```python
def generate_document(
    requested_paths: list[str],
    base_dir: Path,
    *,
    session_manager: SessionManager | None = None,
    sanitizer: InputSanitizer | None = None,
    workflow: _WorkflowProtocol | None = None,
) -> GenerateResult
```

**Parameters:**
- `requested_paths`: User-requested file paths (strings)
- `base_dir`: Allowed input root (resolved)
- `session_manager`: Optional; defaults to environment-loaded
- `sanitizer`: Optional; defaults to environment-loaded
- `workflow`: Optional; defaults to create_document_workflow()

**Returns:**
```python
{
    "success": bool,           # True if workflow completed
    "session_id": str,         # UUID of created session
    "output_path": str,        # Path to output DOCX
    "error": str,              # Error message if failed
    "validation_errors": list, # File validation errors
    "messages": list[str],     # Status messages
}
```

### Session Directory Structure

```
{docs_base_path}/
├── sessions/
│   └── {uuid}/
│       ├── inputs/           # Copied input files
│       ├── assets/            # Copied images
│       ├── checkpoints/       # Version snapshots
│       └── logs/              # Session logs
└── archive/
    └── {uuid}/               # Archived sessions (on success)
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run E2E tests only
uv run pytest tests/e2e/ -v

# Run integration tests only
uv run pytest tests/integration/ -v

# Run specific test file
uv run pytest tests/test_entry.py -v

# Run with coverage
uv run pytest tests/ --cov=backend --cov-report=term-missing
```

## Development

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
MYPYPATH=src uv run mypy -p backend
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCS_BASE_PATH` | Base directory for sessions | `./docs` |
| `SESSIONS_DIR` | Sessions subdirectory name | `sessions` |
| `ARCHIVE_DIR` | Archive subdirectory name | `archive` |
| `INPUT_MAX_FILE_SIZE_BYTES` | Max input file size | 100MB |
| `INPUT_ALLOWED_EXTENSIONS` | Allowed file extensions | `[".txt", ".log", ".md"]` |
| `NODE_PATH` | Override for Node.js executable | `node` |
| `CONVERTER_JS_PATH` | Override for converter.js | `src/node/converter.js` |
| `CONVERSION_TIMEOUT_SECONDS` | DOCX conversion timeout | 120 |

## Troubleshooting

### Common Issues

**"No valid files" error**
- Check that file paths exist and are within base_dir
- Verify file extensions are allowed

**"Session not found" error**
- Session directories are auto-cleaned on failure
- Re-run the request to create a new session

**LLM connection errors**
- Check API key is set (ANTHROPIC_API_KEY or similar)
- Verify network connectivity

**Conversion timeout**
- Increase `CONVERSION_TIMEOUT_SECONDS` for large documents
- Check Node.js is installed and accessible

### Debug Logging

Enable debug logging by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Plans

- Web API layer (FastAPI)
- CLI interface
- Real-time progress updates
- Custom template support
- Batch processing
