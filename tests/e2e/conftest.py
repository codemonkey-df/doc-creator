"""Shared fixtures for e2e tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest



@pytest.fixture
def temp_session_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """GIVEN temporary session directory with required subdirs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_path = Path(tmpdir) / "sessions" / "test-session"
        session_path.mkdir(parents=True)
        for subdir in ["inputs", "assets", "checkpoints", "logs"]:
            (session_path / subdir).mkdir(exist_ok=True)
        yield session_path


@pytest.fixture
def sample_input_files(temp_session_dir: Path) -> list[str]:
    """GIVEN sample input files in session inputs directory."""
    input_dir = temp_session_dir / "inputs"

    # Create sample input files
    files = ["chapter1.txt", "chapter2.txt"]
    for filename in files:
        (input_dir / filename).write_text(f"Content of {filename}", encoding="utf-8")

    return files


@pytest.fixture
def mock_llm_responses() -> MagicMock:
    """GIVEN mocked LLM that returns predefined responses."""
    mock = MagicMock()

    # First call: agent generates content and calls create_checkpoint
    mock.invoke.return_value = MagicMock(
        content="I've created the first chapter.",
        tool_calls=[
            {
                "name": "create_checkpoint",
                "args": {"label": "chapter1"},
            }
        ],
    )

    return mock


@pytest.fixture
def sample_markdown_content() -> str:
    """GIVEN sample valid markdown content."""
    return """# Test Document

## Introduction

This is a test document.

```python
def hello():
    print("Hello, world!")
```

## Conclusion

End of document.
"""
