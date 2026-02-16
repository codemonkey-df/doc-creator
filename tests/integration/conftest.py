"""Shared fixtures for integration tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from typing import Generator

import pytest

from backend.utils.session_manager import SessionManager


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
