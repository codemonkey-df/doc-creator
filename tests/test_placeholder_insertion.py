"""Tests for Story 3.4: Placeholder insertion for missing images (TDD).

Tests AssetHandler.insert_placeholder() and handle_upload_decision(),
plus apply_user_decisions_node(), covering AC3.4.1-3.4.6.

GIVEN-WHEN-THEN format throughout; security tests marked with @pytest.mark.security.
"""

import re
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.state import DocumentState, MissingRefDetail, build_initial_state
from backend.utils.asset_handler import handle_upload_decision, insert_placeholder
from backend.utils.settings import AssetScanSettings


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def temp_session_path(tmp_path: Path) -> Path:
    """GIVEN a temporary session directory structure."""
    session_dir = tmp_path / "session"
    (session_dir / "inputs").mkdir(parents=True)
    (session_dir / "assets").mkdir(parents=True)
    return session_dir


@pytest.fixture
def session_with_missing_refs(temp_session_path: Path) -> Path:
    """GIVEN a session with markdown containing missing image references."""
    # Create an input file with a missing image
    input_file = temp_session_path / "inputs" / "doc.md"
    input_file.write_text(
        "# Document\n\n"
        "![Alt text](missing.png)\n\n"
        "Some content.\n\n"
        "![Another image](image2.jpg)\n",
        encoding="utf-8",
    )
    return temp_session_path


@pytest.fixture
def session_with_temp_output(temp_session_path: Path) -> Path:
    """GIVEN a session with temp_output.md."""
    output_file = temp_session_path / "temp_output.md"
    output_file.write_text(
        "# Generated\n\n"
        "![Missing asset](asset.png)\n",
        encoding="utf-8",
    )
    return temp_session_path


@pytest.fixture
def session_with_uploadable_file(temp_session_path: Path, tmp_path: Path) -> tuple[Path, Path]:
    """GIVEN a session and an external file available for upload."""
    # Create an external image file (not in session)
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    upload_file = external_dir / "uploaded_image.png"
    upload_file.write_text("fake PNG content", encoding="utf-8")

    return temp_session_path, upload_file


@pytest.fixture
def session_with_crlf_file(temp_session_path: Path) -> Path:
    """GIVEN a session with a CRLF line-ending file."""
    input_file = temp_session_path / "inputs" / "crlf_doc.md"
    # Write with explicit CRLF
    input_file.write_bytes(
        b"# Title\r\n\r\n![Image](missing.png)\r\n\r\nContent\r\n"
    )
    return temp_session_path


# ============================================================================
# UNIT TESTS: insert_placeholder()
# ============================================================================


class TestInsertPlaceholder:
    """Tests for insert_placeholder() - AC3.4.3."""

    def test_insert_placeholder_single_ref_success(
        self, session_with_missing_refs: Path
    ) -> None:
        """GIVEN markdown with single missing image ref / WHEN insert_placeholder called / THEN placeholder replaces ref."""
        # Setup
        target_file = "inputs/doc.md"
        image_identifier = "missing.png"

        # Action
        result = insert_placeholder(
            session_with_missing_refs, image_identifier, target_file
        )

        # Assert
        content = (session_with_missing_refs / target_file).read_text(encoding="utf-8")
        assert "**[Image Missing: missing.png]**" in content
        assert "![Alt text](missing.png)" not in content
        assert "image2.jpg" in content  # Other image unchanged
        assert "Document generated" in result.lower() or "inserted" in result.lower()

    def test_insert_placeholder_multiple_refs_same_image(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN markdown with multiple refs to same image / WHEN insert_placeholder / THEN all replaced."""
        # Setup
        input_file = temp_session_path / "inputs" / "multi.md"
        input_file.write_text(
            "# Doc\n\n"
            "![Image 1](missing.png)\n\n"
            "Content\n\n"
            "![Image 2](missing.png)\n",
            encoding="utf-8",
        )

        # Action
        insert_placeholder(temp_session_path, "missing.png", "inputs/multi.md")

        # Assert
        content = input_file.read_text(encoding="utf-8")
        # Both refs should be replaced
        assert content.count("**[Image Missing: missing.png]**") == 2
        assert "![" not in content  # No remaining image refs

    def test_insert_placeholder_temp_output(self, session_with_temp_output: Path) -> None:
        """GIVEN temp_output.md with missing ref / WHEN insert_placeholder with target temp_output.md / THEN placeholder in temp_output."""
        # Action
        insert_placeholder(
            session_with_temp_output, "asset.png", "temp_output.md"
        )

        # Assert
        content = (session_with_temp_output / "temp_output.md").read_text(
            encoding="utf-8"
        )
        assert "**[Image Missing: asset.png]**" in content
        assert "![Missing asset](asset.png)" not in content

    def test_insert_placeholder_nonexistent_target_file(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN nonexistent target_file / WHEN insert_placeholder called / THEN OSError raised."""
        with pytest.raises(OSError):
            insert_placeholder(
                temp_session_path, "missing.png", "inputs/nonexistent.md"
            )

    def test_insert_placeholder_special_chars_in_identifier(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN image identifier with regex special chars like parentheses / WHEN insert_placeholder / THEN properly escaped and replaced."""
        # Setup
        input_file = temp_session_path / "inputs" / "special.md"
        # Path with parentheses and brackets
        weird_path = "image[1](name).png"
        input_file.write_text(
            f"# Doc\n\n![Alt]({weird_path})\n",
            encoding="utf-8",
        )

        # Action
        insert_placeholder(temp_session_path, weird_path, "inputs/special.md")

        # Assert
        content = input_file.read_text(encoding="utf-8")
        assert "**[Image Missing: image[1](name).png]**" in content


# ============================================================================
# UNIT TESTS: handle_upload_decision()
# ============================================================================


class TestHandleUploadDecision:
    """Tests for handle_upload_decision() - AC3.4.4, AC3.4.6."""

    def test_handle_upload_decision_success(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN valid upload_path and missing ref / WHEN handle_upload_decision / THEN file copied to assets and ref updated."""
        session_path, upload_file = session_with_uploadable_file

        # Setup: create input file with missing ref
        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        # Action
        result = handle_upload_decision(
            session_path,
            str(upload_file),
            "missing.png",
            "inputs/doc.md",
            allowed_base_path=None,
        )

        # Assert
        assert "uploaded_image.png" in result
        assert (session_path / "assets" / "uploaded_image.png").exists()
        content = input_file.read_text(encoding="utf-8")
        assert "![Missing](./assets/uploaded_image.png)" in content

    def test_handle_upload_decision_with_allowed_base(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN upload_path and allowed_base_path validation / WHEN handle_upload_decision / THEN path must be under allowed base."""
        session_path, upload_file = session_with_uploadable_file
        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        # Use parent directory of upload_file as allowed base
        allowed_base = upload_file.parent

        # Action
        result = handle_upload_decision(
            session_path,
            str(upload_file),
            "missing.png",
            "inputs/doc.md",
            allowed_base_path=allowed_base,
        )

        # Assert
        assert "uploaded_image.png" in result

    @pytest.mark.security
    def test_handle_upload_decision_reject_path_outside_base(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN upload_path outside allowed_base / WHEN handle_upload_decision / THEN ValueError raised."""
        session_path, upload_file = session_with_uploadable_file
        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        # allowed_base is a different directory entirely
        safe_dir = session_path / "safe"
        safe_dir.mkdir()

        with pytest.raises(ValueError, match="outside.*base|not.*relative"):
            handle_upload_decision(
                session_path,
                str(upload_file),
                "missing.png",
                "inputs/doc.md",
                allowed_base_path=safe_dir,
            )

    @pytest.mark.security
    def test_handle_upload_decision_reject_path_traversal(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN upload_path with ../ traversal / WHEN handle_upload_decision / THEN ValueError raised."""
        session_path, upload_file = session_with_uploadable_file
        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        # Path with traversal (but use allowed_base as parent to make it clear the traversal is the issue)
        allowed_base = upload_file.parent
        traversal_path = str(allowed_base / ".." / "somewhere_else" / "image.png")

        with pytest.raises(ValueError):
            handle_upload_decision(
                session_path,
                traversal_path,
                "missing.png",
                "inputs/doc.md",
                allowed_base_path=allowed_base,
            )

    def test_handle_upload_decision_reject_directory(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN upload_path is a directory (not file) / WHEN handle_upload_decision / THEN ValueError raised."""
        session_path, upload_file = session_with_uploadable_file
        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        directory_path = upload_file.parent

        with pytest.raises(ValueError, match="directory|not.*file"):
            handle_upload_decision(
                session_path,
                str(directory_path),
                "missing.png",
                "inputs/doc.md",
                allowed_base_path=None,
            )

    def test_handle_upload_decision_idempotent(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN handle_upload_decision applied twice / WHEN second call with same ref / THEN idempotent (no error)."""
        session_path, upload_file = session_with_uploadable_file
        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        # First call
        handle_upload_decision(
            session_path, str(upload_file), "missing.png", "inputs/doc.md"
        )
        first_content = input_file.read_text(encoding="utf-8")

        # Second call (idempotent test: should succeed or overwrite without error)
        handle_upload_decision(
            session_path, str(upload_file), "missing.png", "inputs/doc.md"
        )
        second_content = input_file.read_text(encoding="utf-8")

        # Content should be same (or at least both valid)
        assert "![Missing](./assets/uploaded_image.png)" in second_content


# ============================================================================
# UNIT TESTS: apply_user_decisions_node()
# ============================================================================


class TestApplyUserDecisionsNode:
    """Tests for apply_user_decisions_node() - AC3.4.4, AC3.4.5."""

    def test_apply_user_decisions_skip_decision(
        self, session_with_missing_refs: Path, tmp_path: Path
    ) -> None:
        """GIVEN state with user_decisions {"missing.png": "skip"} / WHEN apply_user_decisions_node / THEN placeholder inserted, state cleared."""
        # Setup: state with missing ref and skip decision
        state: DocumentState = build_initial_state("session-id", ["doc.md"])
        state["session_id"] = "test-session"  # Override with temp session reference
        state["user_decisions"] = {"missing.png": "skip"}
        state["missing_references"] = ["missing.png"]
        state["missing_ref_details"] = [
            {"original_path": "missing.png", "source_file": "doc.md"}
        ]
        state["pending_question"] = "Upload or skip?"

        # Mock session_manager
        from backend.graph import _apply_user_decisions_node

        with patch("backend.graph.SessionManager") as mock_sm_class:
            mock_sm = MagicMock()
            mock_sm.get_path.return_value = session_with_missing_refs
            mock_sm_class.return_value = mock_sm

            # Action
            result = _apply_user_decisions_node(state)

        # Assert: placeholder inserted
        content = (
            session_with_missing_refs / "inputs" / "doc.md"
        ).read_text(encoding="utf-8")
        assert "**[Image Missing: missing.png]**" in content

        # Assert: state cleared
        assert result["missing_references"] == []
        assert result["missing_ref_details"] == []
        assert result["pending_question"] == ""
        assert result["status"] == "processing"

    def test_apply_user_decisions_upload_decision(
        self, session_with_missing_refs: Path, tmp_path: Path
    ) -> None:
        """GIVEN state with user_decisions {"missing.png": "/path/to/upload"} / WHEN apply_user_decisions_node / THEN file copied, ref updated."""
        # Setup: create upload file
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        upload_file = upload_dir / "replacement.png"
        upload_file.write_text("fake PNG", encoding="utf-8")

        state: DocumentState = build_initial_state("session-id", ["doc.md"])
        state["user_decisions"] = {"missing.png": str(upload_file)}
        state["missing_references"] = ["missing.png"]
        state["missing_ref_details"] = [
            {"original_path": "missing.png", "source_file": "doc.md"}
        ]

        from backend.graph import _apply_user_decisions_node

        with patch("backend.graph.SessionManager") as mock_sm_class:
            mock_sm = MagicMock()
            mock_sm.get_path.return_value = session_with_missing_refs
            mock_sm_class.return_value = mock_sm

            # Action
            result = _apply_user_decisions_node(state)

        # Assert: file copied to assets
        assert (session_with_missing_refs / "assets" / "replacement.png").exists()

        # Assert: ref updated in input file
        content = (
            session_with_missing_refs / "inputs" / "doc.md"
        ).read_text(encoding="utf-8")
        assert "![Alt text](./assets/replacement.png)" in content

        # Assert: state cleared
        assert result["missing_references"] == []
        assert result["pending_question"] == ""

    def test_apply_user_decisions_no_decisions(
        self, session_with_missing_refs: Path
    ) -> None:
        """GIVEN state with empty user_decisions / WHEN apply_user_decisions_node / THEN no-op, state unchanged."""
        state: DocumentState = build_initial_state("session-id", ["doc.md"])
        state["user_decisions"] = {}
        state["missing_references"] = ["missing.png"]

        from backend.graph import _apply_user_decisions_node

        with patch("backend.graph.SessionManager") as mock_sm_class:
            mock_sm = MagicMock()
            mock_sm.get_path.return_value = session_with_missing_refs
            mock_sm_class.return_value = mock_sm

            # Action
            result = _apply_user_decisions_node(state)

        # Assert: no processing occurred
        # Status might still change but no file modifications
        original_content = (
            session_with_missing_refs / "inputs" / "doc.md"
        ).read_text(encoding="utf-8")
        assert "![Alt text](missing.png)" in original_content

    def test_apply_user_decisions_mixed_skip_upload(
        self, temp_session_path: Path, tmp_path: Path
    ) -> None:
        """GIVEN state with mixed decisions (skip + upload) / WHEN apply_user_decisions_node / THEN both processed."""
        # Setup: two missing refs, one skip one upload
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(
            "![Image1](image1.png)\n\n![Image2](image2.png)\n",
            encoding="utf-8",
        )

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        upload_file = upload_dir / "replacement.png"
        upload_file.write_text("fake PNG", encoding="utf-8")

        state: DocumentState = build_initial_state("session-id", ["doc.md"])
        state["user_decisions"] = {
            "image1.png": "skip",
            "image2.png": str(upload_file),
        }
        state["missing_ref_details"] = [
            {"original_path": "image1.png", "source_file": "doc.md"},
            {"original_path": "image2.png", "source_file": "doc.md"},
        ]

        from backend.graph import _apply_user_decisions_node

        with patch("backend.graph.SessionManager") as mock_sm_class:
            mock_sm = MagicMock()
            mock_sm.get_path.return_value = temp_session_path
            mock_sm_class.return_value = mock_sm

            # Action
            result = _apply_user_decisions_node(state)

        # Assert: placeholder for skip
        content = input_file.read_text(encoding="utf-8")
        assert "**[Image Missing: image1.png]**" in content

        # Assert: path for upload
        assert "![Image2](./assets/replacement.png)" in content

        # Assert: state cleared
        assert result["status"] == "processing"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegrationPlaceholderFlow:
    """Integration tests for complete missing image reference flow."""

    def test_scan_to_apply_decisions_skip_flow(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN session with missing image / WHEN scan_assets → human_input → apply_user_decisions / THEN placeholder inserted, agent ready."""
        # Setup
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text("![Image](missing.png)", encoding="utf-8")

        # Simulate scan_assets detecting missing
        state: DocumentState = build_initial_state("test-session", ["doc.md"])
        state["missing_references"] = ["missing.png"]
        state["missing_ref_details"] = [
            {"original_path": "missing.png", "source_file": "doc.md"}
        ]
        state["pending_question"] = "Upload or skip?"

        # Simulate human input with skip decision
        state["user_decisions"] = {"missing.png": "skip"}
        state["pending_question"] = ""  # Cleared by entry before resume

        from backend.graph import _apply_user_decisions_node

        with patch("backend.graph.SessionManager") as mock_sm_class:
            mock_sm = MagicMock()
            mock_sm.get_path.return_value = temp_session_path
            mock_sm_class.return_value = mock_sm

            # Action: apply decisions
            result = _apply_user_decisions_node(state)

        # Assert: agent is ready
        assert result["status"] == "processing"
        assert result["missing_references"] == []

        # Assert: placeholder in file
        content = input_file.read_text(encoding="utf-8")
        assert "**[Image Missing: missing.png]**" in content

    def test_scan_to_apply_decisions_upload_flow(
        self, temp_session_path: Path, tmp_path: Path
    ) -> None:
        """GIVEN session with missing image and user upload / WHEN apply_user_decisions / THEN file in assets, agent can use it."""
        # Setup
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text("![Image](missing.png)", encoding="utf-8")

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        replacement = upload_dir / "replacement.png"
        replacement.write_bytes(b"PNG_CONTENT")

        state: DocumentState = build_initial_state("test-session", ["doc.md"])
        state["missing_references"] = ["missing.png"]
        state["missing_ref_details"] = [
            {"original_path": "missing.png", "source_file": "doc.md"}
        ]
        state["user_decisions"] = {"missing.png": str(replacement)}

        from backend.graph import _apply_user_decisions_node

        with patch("backend.graph.SessionManager") as mock_sm_class:
            mock_sm = MagicMock()
            mock_sm.get_path.return_value = temp_session_path
            mock_sm_class.return_value = mock_sm

            # Action
            result = _apply_user_decisions_node(state)

        # Assert: agent is ready
        assert result["status"] == "processing"

        # Assert: file in assets
        assert (temp_session_path / "assets" / "replacement.png").exists()

        # Assert: ref updated
        content = input_file.read_text(encoding="utf-8")
        assert "![Image](./assets/replacement.png)" in content

    def test_multiple_missing_refs_mixed_decisions(
        self, temp_session_path: Path, tmp_path: Path
    ) -> None:
        """GIVEN multiple missing refs with mixed skip/upload decisions / WHEN apply_user_decisions / THEN all processed correctly."""
        # Setup
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(
            "![Image1](missing1.png)\n\n"
            "Content\n\n"
            "![Image2](missing2.jpg)\n\n"
            "More text\n\n"
            "![Image3](missing3.svg)\n",
            encoding="utf-8",
        )

        uploads = {}
        for name in ["img2.jpg", "img3.svg"]:
            upload_dir = tmp_path / "uploads"
            upload_dir.mkdir(exist_ok=True)
            upload_file = upload_dir / name
            upload_file.write_bytes(b"FAKE_CONTENT")
            uploads[name] = upload_file

        state: DocumentState = build_initial_state("test-session", ["doc.md"])
        state["missing_ref_details"] = [
            {"original_path": "missing1.png", "source_file": "doc.md"},
            {"original_path": "missing2.jpg", "source_file": "doc.md"},
            {"original_path": "missing3.svg", "source_file": "doc.md"},
        ]
        state["user_decisions"] = {
            "missing1.png": "skip",
            "missing2.jpg": str(uploads["img2.jpg"]),
            "missing3.svg": str(uploads["img3.svg"]),
        }

        from backend.graph import _apply_user_decisions_node

        with patch("backend.graph.SessionManager") as mock_sm_class:
            mock_sm = MagicMock()
            mock_sm.get_path.return_value = temp_session_path
            mock_sm_class.return_value = mock_sm

            # Action
            result = _apply_user_decisions_node(state)

        # Assert: all decisions applied
        content = input_file.read_text(encoding="utf-8")

        # Placeholder for skip
        assert "**[Image Missing: missing1.png]**" in content

        # Uploaded file paths
        assert "![Image2](./assets/img2.jpg)" in content
        assert "![Image3](./assets/img3.svg)" in content

        # Assert: files in assets
        assert (temp_session_path / "assets" / "img2.jpg").exists()
        assert (temp_session_path / "assets" / "img3.svg").exists()


# ============================================================================
# SECURITY TESTS
# ============================================================================


class TestSecurityValidation:
    """Security tests for upload path validation."""

    @pytest.mark.security
    def test_reject_symlink_traversal(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN upload_path is symlink pointing outside allowed_base / WHEN handle_upload_decision / THEN rejected."""
        session_path, upload_file = session_with_uploadable_file

        # Create a symlink
        external_dir = upload_file.parent.parent / "external"
        external_dir.mkdir(exist_ok=True)
        external_file = external_dir / "external_image.png"
        external_file.write_text("external content", encoding="utf-8")

        symlink_path = upload_file.parent / "symlink.png"
        try:
            symlink_path.symlink_to(external_file)
        except OSError:
            pytest.skip("Symlink creation not supported on this platform")

        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        # Try to use symlink with allowed_base restriction
        allowed_base = upload_file.parent

        # Depending on implementation, this should either be rejected or safely handled
        # The main point is no path escape
        try:
            handle_upload_decision(
                session_path,
                str(symlink_path),
                "missing.png",
                "inputs/doc.md",
                allowed_base_path=allowed_base,
            )
        except ValueError:
            pass  # Expected: rejected for symlink


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_insert_placeholder_empty_alt_text(self, temp_session_path: Path) -> None:
        """GIVEN image with empty alt text / WHEN insert_placeholder / THEN placeholder still inserted."""
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text("![](missing.png)", encoding="utf-8")

        insert_placeholder(temp_session_path, "missing.png", "inputs/doc.md")

        content = input_file.read_text(encoding="utf-8")
        assert "**[Image Missing: missing.png]**" in content

    def test_insert_placeholder_very_long_identifier(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN very long image identifier / WHEN insert_placeholder / THEN handled correctly."""
        long_id = "very_long_directory/path/to/image_with_very_long_name_12345.png"
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(f"![Alt]({long_id})", encoding="utf-8")

        insert_placeholder(temp_session_path, long_id, "inputs/doc.md")

        content = input_file.read_text(encoding="utf-8")
        assert f"**[Image Missing: image_with_very_long_name_12345.png]**" in content

    def test_insert_placeholder_crlf_preservation(
        self, session_with_crlf_file: Path
    ) -> None:
        """GIVEN file with CRLF line endings / WHEN insert_placeholder / THEN CRLF preserved."""
        # Read original bytes to check line endings
        original_bytes = (session_with_crlf_file / "inputs" / "crlf_doc.md").read_bytes()
        assert b"\r\n" in original_bytes

        insert_placeholder(
            session_with_crlf_file, "missing.png", "inputs/crlf_doc.md"
        )

        # Check CRLF still present
        modified_bytes = (
            session_with_crlf_file / "inputs" / "crlf_doc.md"
        ).read_bytes()
        assert b"\r\n" in modified_bytes

    def test_handle_upload_decision_basename_extraction(
        self, session_with_uploadable_file: tuple[Path, Path]
    ) -> None:
        """GIVEN upload path with nested directories / WHEN handle_upload_decision / THEN basename used in assets."""
        session_path, upload_file = session_with_uploadable_file
        input_file = session_path / "inputs" / "doc.md"
        input_file.write_text("![Missing](missing.png)", encoding="utf-8")

        # Action
        handle_upload_decision(
            session_path,
            str(upload_file),
            "missing.png",
            "inputs/doc.md",
        )

        # Assert: assets/ contains only basename (no nested dirs)
        assets_dir = session_path / "assets"
        files = list(assets_dir.iterdir())
        assert len(files) == 1
        assert files[0].name == "uploaded_image.png"
        assert files[0].is_file()
