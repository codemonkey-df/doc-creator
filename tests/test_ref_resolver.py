"""Tests for reference resolver module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.scanner.ref_scanner import Ref
from src.tui.state import AppState


def test_resolve_refs_all_skipped():
    """Test that all refs are skipped when no resolution provided."""
    from src.resolver.ref_resolver import resolve_refs

    refs = [
        Ref(
            type="image",
            original="![alt](image.png)",
            resolved_path=None,
            status="found",
            source_file=Path("test.md"),
            line_number=1,
        )
    ]
    state = AppState()
    result = resolve_refs(refs, state)

    # Verify the result has the expected attributes
    assert hasattr(result, "skipped")
    assert hasattr(result, "provided")
    assert hasattr(result, "to_summarize")
    assert len(result.skipped) == 1
    assert result.skipped[0] == refs[0]
    assert result.provided == []
    assert result.to_summarize == []


def test_placeholder_format_image():
    """Test placeholder format for image refs."""
    from src.resolver.ref_resolver import format_placeholder

    ref = Ref(
        type="image",
        original="![alt](diagram.png)",
        resolved_path=None,
        status="found",
        source_file=Path("test.md"),
        line_number=1,
    )

    placeholder = format_placeholder(ref)
    assert placeholder == "[Image: diagram.png]"


def test_placeholder_format_url():
    """Test placeholder format for URL refs."""
    from src.resolver.ref_resolver import format_placeholder

    ref = Ref(
        type="url",
        original="https://example.com/doc",
        resolved_path=None,
        status="external",
        source_file=Path("test.md"),
        line_number=1,
    )

    placeholder = format_placeholder(ref)
    assert placeholder == "[External URL: https://example.com/doc]"


def test_placeholder_format_path():
    """Test placeholder format for path refs."""
    from src.resolver.ref_resolver import format_placeholder

    ref = Ref(
        type="path",
        original="[Link](other.md)",
        resolved_path=None,
        status="found",
        source_file=Path("test.md"),
        line_number=1,
    )

    placeholder = format_placeholder(ref)
    assert placeholder == "[External Path: other.md]"


def test_resolve_refs_empty():
    """Test that empty refs list returns empty ResolvedContext."""
    from src.resolver.ref_resolver import resolve_refs

    state = AppState()
    result = resolve_refs([], state)

    # Verify the result has the expected attributes
    assert hasattr(result, "skipped")
    assert hasattr(result, "provided")
    assert hasattr(result, "to_summarize")
    assert result.skipped == []
    assert result.provided == []
    assert result.to_summarize == []


def test_provide_path_success(tmp_path):
    """Test that valid path copies file and returns updated ref."""
    from src.resolver.ref_resolver import provide_path

    # Create source file
    source_file = tmp_path / "source.md"
    source_file.write_text("# Source Content")

    # Create input directory
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    # Create ref
    ref = Ref(
        type="path",
        original="[Link](source.md)",
        resolved_path=None,
        status="found",
        source_file=Path("test.md"),
        line_number=1,
    )

    # Call provide_path
    updated_ref, success = provide_path(ref, input_dir, str(source_file))

    # Verify success
    assert success is True
    assert updated_ref.status == "provided"
    assert updated_ref.resolved_path == input_dir / "source.md"
    assert updated_ref.resolved_path.exists()
    assert updated_ref.resolved_path.read_text() == "# Source Content"


def test_provide_path_file_not_found(tmp_path):
    """Test that invalid path returns error indicator."""
    from src.resolver.ref_resolver import provide_path

    # Create input directory
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    # Create ref
    ref = Ref(
        type="path",
        original="[Link](nonexistent.md)",
        resolved_path=None,
        status="found",
        source_file=Path("test.md"),
        line_number=1,
    )

    # Call provide_path with non-existent file
    updated_ref, success = provide_path(ref, input_dir, "/nonexistent/path.md")

    # Verify failure
    assert success is False
    assert updated_ref.status == "error"


def test_summarize_ref_adds_to_summarize(tmp_path):
    """Test that content is added to to_summarize list."""
    from src.config import LlmConfig
    from src.resolver.ref_resolver import summarize_ref

    # Create source file
    source_file = tmp_path / "external.md"
    source_file.write_text("# External Content\n\nThis is some content to summarize.")

    # Create ref with resolved path
    ref = Ref(
        type="path",
        original="[Link](external.md)",
        resolved_path=source_file,
        status="found",
        source_file=Path("chapter1.md"),
        line_number=5,
    )

    # Mock config
    config = LlmConfig()

    # Mock call_llm to return a summary
    with patch("src.resolver.ref_resolver.call_llm") as mock_call_llm:
        mock_call_llm.return_value = (
            "This is a concise summary of the external content."
        )

        file_path, summary = summarize_ref(ref, config)

        # Verify summary was generated
        assert file_path == str(source_file)
        assert summary == "This is a concise summary of the external content."
        mock_call_llm.assert_called_once()


def test_url_ref_cannot_summarize():
    """Test that URL refs raise ValueError when summarized."""
    from src.config import LlmConfig
    from src.resolver.ref_resolver import summarize_ref

    # Create URL ref
    ref = Ref(
        type="url",
        original="https://example.com/doc",
        resolved_path=None,
        status="external",
        source_file=Path("test.md"),
        line_number=1,
    )

    config = LlmConfig()

    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot summarize URL references"):
        summarize_ref(ref, config)


def test_resolve_refs_integration(tmp_path):
    """Test full flow with provided and summarized refs."""
    from src.resolver.ref_resolver import resolve_refs, provide_path

    # Create input directory
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    # Create source files
    source_file1 = tmp_path / "provided.md"
    source_file1.write_text("# Provided Content")

    source_file2 = tmp_path / "to_summarize.md"
    source_file2.write_text("# Content to Summarize")

    # Create refs
    ref1 = Ref(
        type="path",
        original="[Link](provided.md)",
        resolved_path=None,
        status="found",
        source_file=Path("test.md"),
        line_number=1,
    )

    ref2 = Ref(
        type="path",
        original="[Link](to_summarize.md)",
        resolved_path=source_file2,
        status="found",
        source_file=Path("chapter1.md"),
        line_number=5,
    )

    # Provide path for ref1
    provided_ref, _ = provide_path(ref1, input_dir, str(source_file1))

    # Mock summarize for ref2
    summarized_refs = [(str(source_file2), "This is a summary.")]

    # Create state
    state = AppState()

    # Resolve refs with provided and summarized
    result = resolve_refs([ref1, ref2], state, [provided_ref], summarized_refs)

    # Verify provided ref is in provided list
    assert len(result.provided) == 1
    assert result.provided[0].original == "[Link](provided.md)"

    # Verify summarized ref is in to_summarize list
    assert len(result.to_summarize) == 1
    assert result.to_summarize[0][0] == str(source_file2)

    # Verify no refs are skipped
    assert result.skipped == []
