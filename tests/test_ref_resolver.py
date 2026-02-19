"""Tests for reference resolver module."""

from src.scanner.ref_scanner import Ref
from src.llm.generator import ResolvedContext
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
            source_file="test.md",
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
        source_file="test.md",
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
        source_file="test.md",
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
        source_file="test.md",
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
