"""Shared fixtures for integration tests."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock
from typing import Generator

import pytest

from backend.state import DocumentState, build_initial_state
from backend.utils.session_manager import SessionManager


@pytest.fixture
def temp_session_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """GIVEN temporary session directory with required subdirs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_path = Path(tmpdir) / "sessions" / str(uuid.uuid4())
        session_path.mkdir(parents=True)
        for subdir in ["inputs", "assets", "checkpoints", "logs"]:
            (session_path / subdir).mkdir(exist_ok=True)
        yield session_path


@pytest.fixture
def mock_session_manager(temp_session_dir: Path) -> SessionManager:
    """GIVEN mocked SessionManager that uses temp directory."""
    sm = MagicMock(spec=SessionManager)
    sm.get_path.return_value = temp_session_dir
    return sm


@pytest.fixture
def session_manager_for_integration(temp_session_dir: Path) -> SessionManager:
    """GIVEN a real SessionManager that uses temp directory."""
    sm = SessionManager()

    # Override get_path to return our temp directory
    def mock_get_path(session_id: str) -> Path:
        return temp_session_dir

    sm.get_path = mock_get_path
    return sm


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


@pytest.fixture
def sample_markdown_with_invalid() -> str:
    """GIVEN sample invalid markdown content (unclosed fence)."""
    return """# Test Document

## Introduction

```python
def hello():
    print("Hello, world!")
"""


@pytest.fixture
def sample_state(temp_session_dir: Path) -> DocumentState:
    """GIVEN a DocumentState created by build_initial_state."""
    session_id = str(uuid.uuid4())
    return build_initial_state(session_id=session_id, input_files=["doc.md"])


@pytest.fixture
def session_with_temp_output(
    temp_session_dir: Path, sample_markdown_content: str
) -> tuple[Path, DocumentState]:
    """GIVEN session with temp_output.md created in session directory.

    Returns tuple of (session_path, initial_state).
    """
    session_id = str(uuid.uuid4())
    temp_output = temp_session_dir / "temp_output.md"
    temp_output.write_text(sample_markdown_content, encoding="utf-8")

    # Create initial state with session_id pointing to temp session
    initial_state = build_initial_state(session_id=session_id, input_files=["doc.md"])

    return temp_session_dir, initial_state
