"""Shared fixtures for e2e tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest

from langchain_core.messages import AIMessage

from backend.graph import create_document_workflow
from backend.state import DocumentState, build_initial_state
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
def sample_input_files(temp_session_dir: Path) -> list[str]:
    """GIVEN sample input files in session inputs directory."""
    input_dir = temp_session_dir / "inputs"

    # Create sample input files
    files = ["chapter1.txt", "chapter2.txt"]
    for filename in files:
        (input_dir / filename).write_text(f"Content of {filename}", encoding="utf-8")

    return files


@pytest.fixture
def mock_llm() -> MagicMock:
    """GIVEN mocked LLM that returns configurable AIMessage responses."""
    mock = MagicMock()
    # Make bind_tools return self for chaining
    mock.bind_tools.return_value = mock
    # Default: completion with no tool calls
    mock.invoke.return_value = AIMessage(content="Generation complete.")
    return mock


@pytest.fixture
def mock_llm_with_checkpoint() -> MagicMock:
    """GIVEN mocked LLM that returns AIMessage with create_checkpoint tool call."""
    mock = MagicMock()
    mock.bind_tools.return_value = mock
    mock.invoke.return_value = AIMessage(
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


@pytest.fixture
def compiled_graph(temp_session_dir: Path) -> Any:
    """GIVEN compiled document workflow with mocked SessionManager."""

    # Create a mock session manager that returns our temp directory
    class MockSessionManager:
        def get_path(self, session_id: str) -> Path:
            return temp_session_dir

    # Create the workflow with mocked session manager
    workflow = create_document_workflow(session_manager=MockSessionManager())

    return workflow


@pytest.fixture
def initial_state_for_graph(
    temp_session_dir: Path, sample_input_files: list[str]
) -> DocumentState:
    """GIVEN initial DocumentState ready for graph invocation."""
    session_id = "test-session-123"
    initial = build_initial_state(session_id=session_id, input_files=sample_input_files)

    # Override session manager to use temp directory
    sm = SessionManager()
    original_get_path = sm.get_path

    def mock_get_path(sid: str) -> Path:
        if sid == session_id:
            return temp_session_dir
        return original_get_path(sid)

    sm.get_path = mock_get_path

    return initial
