"""Integration tests for scan_assets to agent flow (Epics 1-3).

Tests multi-node flows: scan_assets → agent routing with mocked LLM.
"""

from __future__ import annotations

from pathlib import Path


from backend.graph import _scan_assets_impl
from backend.state import DocumentState


class TestScanToAgentFlow:
    """Test scan_assets node routing to agent or human_input."""

    def test_scan_no_missing_images_routes_to_agent(
        self, temp_session_dir: Path, sample_state: DocumentState
    ) -> None:
        """GIVEN input files without image refs WHEN scan_assets runs THEN status=processing, no pending_question."""
        # Setup: create input file without image refs
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text("# Test\n\nNo images here.", encoding="utf-8")

        # Override session manager
        from backend.utils.session_manager import SessionManager

        sm = SessionManager()

        def mock_get_path(sid: str) -> Path:
            return temp_session_dir

        sm.get_path = mock_get_path

        # Execute scan_assets
        state = sample_state.copy()
        state["input_files"] = ["doc.md"]
        result = _scan_assets_impl(state, sm)

        # Assert: routes to agent (no pending_question)
        assert result["status"] == "processing"
        assert result["pending_question"] == ""
        assert len(result["missing_references"]) == 0

    def test_scan_missing_images_sets_pending_question(
        self, temp_session_dir: Path, sample_state: DocumentState
    ) -> None:
        """GIVEN input file with missing image ref WHEN scan_assets runs THEN pending_question set, routes to human_input."""
        # Setup: create input file with missing image ref
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text(
            "# Test\n\n![missing image](missing.png)", encoding="utf-8"
        )

        # Override session manager
        from backend.utils.session_manager import SessionManager

        sm = SessionManager()

        def mock_get_path(sid: str) -> Path:
            return temp_session_dir

        sm.get_path = mock_get_path

        # Execute scan_assets
        state = sample_state.copy()
        state["input_files"] = ["doc.md"]
        result = _scan_assets_impl(state, sm)

        # Assert: missing ref detected, pending_question set
        assert len(result["missing_references"]) == 1
        assert "missing.png" in result["missing_references"]
        assert result["pending_question"] != ""
        assert "missing image" in result["pending_question"].lower()

    def test_scan_copies_found_images_to_assets(
        self, temp_session_dir: Path, sample_state: DocumentState
    ) -> None:
        """GIVEN input file with existing image ref WHEN scan_assets runs THEN image copied to assets/, refs rewritten."""
        # Setup: create input file with image ref and actual image
        input_file = temp_session_dir / "inputs" / "doc.md"
        image_file = temp_session_dir / "inputs" / "test.png"

        # Create a simple PNG file (1x1 transparent)
        image_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        input_file.write_text("# Test\n\n![test image](test.png)", encoding="utf-8")

        # Override session manager
        from backend.utils.session_manager import SessionManager

        sm = SessionManager()

        def mock_get_path(sid: str) -> Path:
            return temp_session_dir

        sm.get_path = mock_get_path

        # Execute scan_assets
        state = sample_state.copy()
        state["input_files"] = ["doc.md"]
        result = _scan_assets_impl(state, sm)

        # Assert: image copied to assets/
        assets_dir = temp_session_dir / "assets"
        assert assets_dir.exists()
        assert (assets_dir / "test.png").exists(), "Image should be copied to assets/"

        # Assert: ref rewritten in input file
        rewritten_content = input_file.read_text(encoding="utf-8")
        assert "./assets/test.png" in rewritten_content, (
            "Ref should be rewritten to ./assets/test.png"
        )

        # Assert: found_image_refs populated
        assert len(result["found_image_refs"]) == 1
        assert result["found_image_refs"][0]["original_path"] == "test.png"


class TestScanRoutingDecision:
    """Test routing decisions based on scan results."""

    def test_scan_with_missing_refs_returns_missing_list(
        self, temp_session_dir: Path, sample_state: DocumentState
    ) -> None:
        """GIVEN multiple missing image refs WHEN scan_assets runs THEN all tracked in missing_references."""
        # Setup: create input files with missing refs
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text(
            "# Test\n\n![img1](missing1.png)\n\n![img2](missing2.png)",
            encoding="utf-8",
        )

        from backend.utils.session_manager import SessionManager

        sm = SessionManager()

        def mock_get_path(sid: str) -> Path:
            return temp_session_dir

        sm.get_path = mock_get_path

        # Execute scan_assets
        state = sample_state.copy()
        state["input_files"] = ["doc.md"]
        result = _scan_assets_impl(state, sm)

        # Assert: both missing refs tracked
        assert len(result["missing_references"]) == 2
        assert "missing1.png" in result["missing_references"]
        assert "missing2.png" in result["missing_references"]
