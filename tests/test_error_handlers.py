"""Tests for Error Handlers - Story 6.2.

GIVEN-WHEN-THEN pattern with pytest fixtures.
"""

import pytest
from pathlib import Path

from backend.error_handlers import (
    fix_unclosed_code_block,
    fix_invalid_utf8,
    insert_placeholder,
    fix_heading_hierarchy,
)
from backend.error_handlers import (
    syntax_handler,
    encoding_handler,
    asset_handler,
    structural_handler,
)
from backend.utils.session_manager import SessionManager
from backend.utils.settings import SessionSettings


# --- Fixtures ---


@pytest.fixture
def temp_base(tmp_path: Path) -> Path:
    """GIVEN a temporary base directory for sessions."""
    return tmp_path.resolve()


@pytest.fixture
def session_settings(temp_base: Path) -> SessionSettings:
    """GIVEN SessionSettings with temp base (no real ./docs touched)."""
    return SessionSettings(
        docs_base_path=temp_base,
        sessions_dir="sessions",
        archive_dir="archive",
    )


@pytest.fixture
def session_manager(session_settings: SessionSettings) -> SessionManager:
    """GIVEN a SessionManager configured with temp base."""
    return SessionManager(settings=session_settings)


@pytest.fixture
def session_with_output(session_manager: SessionManager) -> tuple[str, Path]:
    """GIVEN a created session with temp_output.md."""
    session_id = session_manager.create()
    output_path = session_manager.get_path(session_id) / "temp_output.md"
    output_path.write_text("# Test Document\n\nContent here.", encoding="utf-8")
    return session_id, output_path


@pytest.fixture(autouse=True)
def reset_managers():
    """Reset global session managers before each test."""
    syntax_handler._session_manager = None
    encoding_handler._session_manager = None
    asset_handler._session_manager = None
    structural_handler._session_manager = None
    yield
    syntax_handler._session_manager = None
    encoding_handler._session_manager = None
    asset_handler._session_manager = None
    structural_handler._session_manager = None


# --- SyntaxHandler Tests ---


class TestSyntaxHandlerUnclosedFence:
    """Test fix_unclosed_code_block with unclosed code fences."""

    def test_syntax_handler_unclosed_fence(
        self,
        session_manager: SessionManager,
        session_settings: SessionSettings,
    ) -> None:
        """GIVEN unclosed code fence / WHEN fix_unclosed_code_block / THEN fence is closed."""
        # Set up session with unclosed fence
        syntax_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text(
            "# Test\n\n```python\ncode without closing", encoding="utf-8"
        )

        # When
        result = fix_unclosed_code_block(session_id)

        # Then
        assert "Added closing code fence" in result
        content = output_path.read_text(encoding="utf-8")
        assert content.count("```") == 2

    def test_syntax_handler_no_fence_issue(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN even fence count / WHEN fix_unclosed_code_block / THEN no change."""
        syntax_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text(
            "# Test\n\n```python\ncode\n```\n\nMore content.", encoding="utf-8"
        )

        # When
        result = fix_unclosed_code_block(session_id)

        # Then
        assert "No unclosed code fence found" in result

    def test_syntax_handler_missing_session(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN missing session / WHEN fix_unclosed_code_block / THEN failure string."""
        syntax_handler.set_session_manager(session_manager)
        unknown_id = "00000000-0000-0000-0000-000000000000"

        # When
        result = fix_unclosed_code_block(unknown_id)

        # Then
        assert "Fix failed: session not found" == result


# --- EncodingHandler Tests ---


class TestEncodingHandler:
    """Test fix_invalid_utf8."""

    def test_encoding_handler_invalid_utf8(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN invalid UTF-8 / WHEN fix_invalid_utf8 / THEN cleaned."""
        encoding_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"

        # Write content with invalid UTF-8 bytes
        content = b"# Test\n\nInvalid: \xff\xfe\nEnd."
        output_path.write_bytes(content)

        # When
        result = fix_invalid_utf8(session_id)

        # Then
        assert "Fixed invalid UTF-8 sequences" in result
        # Read back as utf-8 (should not raise)
        new_content = output_path.read_text(encoding="utf-8")
        assert "\ufffd" in new_content  # Replacement character

    def test_encoding_handler_idempotent(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN run twice / WHEN fix_invalid_utf8 / THEN same result."""
        encoding_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text("# Valid UTF-8 content", encoding="utf-8")

        # When - run twice
        result1 = fix_invalid_utf8(session_id)
        result2 = fix_invalid_utf8(session_id)

        # Then
        assert result1 == result2


# --- AssetHandler Tests ---


class TestAssetHandler:
    """Test insert_placeholder."""

    def test_asset_handler_replace_image(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN missing image ref / WHEN insert_placeholder / THEN placeholder."""
        asset_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text(
            "# Test\n\n![logo](assets/logo.png)\n\nText.", encoding="utf-8"
        )

        # When
        result = insert_placeholder(session_id, asset_ref="assets/logo.png")

        # Then
        assert "Replaced" in result
        assert "missing image" in result.lower()
        content = output_path.read_text(encoding="utf-8")
        assert "**[Image Missing: assets/logo.png]**" in content

    def test_asset_handler_no_ref(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN no asset_ref / WHEN insert_placeholder / THEN use unknown_asset."""
        asset_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text(
            "# Test\n\n![image](missing.jpg)\n\nText.", encoding="utf-8"
        )

        # When
        result = insert_placeholder(session_id)

        # Then
        assert "unknown_asset" in result
        content = output_path.read_text(encoding="utf-8")
        assert "**[Image Missing: unknown_asset]**" in content

    def test_asset_handler_no_matching_image(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN no matching image / WHEN insert_placeholder / THEN no change."""
        asset_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text(
            "# Test\n\n![logo](assets/logo.png)\n\nText.", encoding="utf-8"
        )

        # When
        result = insert_placeholder(session_id, asset_ref="different.png")

        # Then
        assert "No matching image reference found" in result
        content = output_path.read_text(encoding="utf-8")
        assert "![logo](assets/logo.png)" in content


# --- StructuralHandler Tests ---


class TestStructuralHandler:
    """Test fix_heading_hierarchy."""

    def test_structural_handler_skip_level(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN H1 then H4 / WHEN fix_heading_hierarchy / THEN H2."""
        structural_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text("# Title\n\n#### Too Deep\n\nContent.", encoding="utf-8")

        # When
        result = fix_heading_hierarchy(session_id)

        # Then
        assert "Fixed" in result
        assert "skipped" in result.lower()
        content = output_path.read_text(encoding="utf-8")
        assert "## Too Deep" in content

    def test_structural_handler_clamp_1_3(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN level > 3 / WHEN fix_heading_hierarchy / THEN clamped to 3."""
        structural_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        # Use headings at levels 4 and 5 which should be clamped to 3
        output_path.write_text(
            "# Title\n\n## Subtitle\n\n#### Level 4\n\n##### Level 5", encoding="utf-8"
        )

        # When
        result = fix_heading_hierarchy(session_id)

        # Then - H2->H4 is +2 (not a skip), but level 4/5 should be clamped to 3
        assert "Clamped" in result
        assert "3" in result
        content = output_path.read_text(encoding="utf-8")
        # Both #### and ##### should become ###
        assert "### Level 4" in content
        assert "### Level 5" in content

    def test_structural_handler_idempotent(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN run twice / WHEN fix_heading_hierarchy / THEN same result."""
        structural_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text(
            "# Title\n\n## Subtitle\n\n### Details", encoding="utf-8"
        )

        # When - run twice
        result1 = fix_heading_hierarchy(session_id)
        result2 = fix_heading_hierarchy(session_id)

        # Then
        assert result1 == result2
        assert "No heading hierarchy issues found" in result1

    def test_structural_handler_h1_to_h3_direct(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN H1 directly to H3 / WHEN fix_heading_hierarchy / THEN valid."""
        structural_handler.set_session_manager(session_manager)
        session_id = session_manager.create()
        output_path = session_manager.get_path(session_id) / "temp_output.md"
        output_path.write_text("# Title\n\n### Section 3\n\nContent.", encoding="utf-8")

        # When
        result = fix_heading_hierarchy(session_id)

        # Then - H1 -> H3 is valid (only +2, not more than +1)
        assert "No heading hierarchy issues found" in result


# --- Missing Session Tests ---


class TestHandlerMissingSession:
    """Test all handlers return failure for missing session."""

    def test_encoding_handler_missing_session(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN missing session / WHEN fix_invalid_utf8 / THEN failure string."""
        encoding_handler.set_session_manager(session_manager)
        unknown_id = "00000000-0000-0000-0000-000000000000"

        result = fix_invalid_utf8(unknown_id)

        assert "Fix failed: session not found" == result

    def test_asset_handler_missing_session(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN missing session / WHEN insert_placeholder / THEN failure string."""
        asset_handler.set_session_manager(session_manager)
        unknown_id = "00000000-0000-0000-0000-000000000000"

        result = insert_placeholder(unknown_id, "test.png")

        assert "Fix failed: session not found" == result

    def test_structural_handler_missing_session(
        self,
        session_manager: SessionManager,
    ) -> None:
        """GIVEN missing session / WHEN fix_heading_hierarchy / THEN failure string."""
        structural_handler.set_session_manager(session_manager)
        unknown_id = "00000000-0000-0000-0000-000000000000"

        result = fix_heading_hierarchy(unknown_id)

        assert "Fix failed: session not found" == result
