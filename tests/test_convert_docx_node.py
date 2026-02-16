"""Unit tests for convert_with_docxjs_node (Story 5.4)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.graph_nodes import convert_with_docxjs_node
from backend.state import DocumentState


class TestConvertWithDocxjsNode:
    """Test cases for the convert_with_docxjs_node function."""

    @pytest.fixture
    def mock_session_manager(self):
        """Mock SessionManager for testing."""
        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_session_path = MagicMock(spec=Path)
            mock_session_path.__truediv__ = lambda self, x: MagicMock(
                spec=Path,
                exists=MagicMock(return_value=True),
                __truediv__=lambda s, y: MagicMock(spec=Path),
            )
            mock_instance.get_path.return_value = mock_session_path
            mock_sm.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def base_state(self) -> DocumentState:
        """Base state for testing."""
        return {
            "session_id": "test-session-123",
            "structure_json_path": "",
            "output_docx_path": "",
            "conversion_attempts": 0,
            "conversion_success": False,
            "last_error": "",
            "status": "converting",
        }

    def test_success_path(self, base_state, monkeypatch, tmp_path):
        """Test successful conversion path."""
        # Create mock structure.json
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        # Mock subprocess.run to return success
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Created DOCX: output.docx"
        mock_result.stderr = ""

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("subprocess.run", return_value=mock_result):
                with patch("shutil.which", return_value="/usr/local/bin/node"):
                    state = {**base_state, "structure_json_path": str(structure_json)}
                    result = convert_with_docxjs_node(state)

        assert result["conversion_success"] is True
        assert "output_docx_path" in result
        assert result["status"] == "quality_checking"
        assert result["conversion_attempts"] == 1

    def test_missing_structure_json(self, base_state, monkeypatch, tmp_path):
        """Test when structure.json is missing."""
        # No structure.json file created
        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("shutil.which", return_value="/usr/local/bin/node"):
                state = {**base_state}
                result = convert_with_docxjs_node(state)

        assert result["conversion_success"] is False
        assert result["last_error"] == "No structure.json"
        assert result["status"] == "error_handling"
        assert result["conversion_attempts"] == 1

    def test_missing_node_executable(self, base_state, monkeypatch, tmp_path):
        """Test when Node.js is not found."""
        # Create mock structure.json
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("shutil.which", return_value=None):
                state = {**base_state, "structure_json_path": str(structure_json)}
                result = convert_with_docxjs_node(state)

        assert result["conversion_success"] is False
        assert result["last_error"] == "Node.js not found"
        assert result["status"] == "error_handling"
        assert result["conversion_attempts"] == 1

    def test_missing_converter_js(self, base_state, monkeypatch, tmp_path):
        """Test when converter.js is not found."""
        # Create mock structure.json
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        # Set CONVERTER_JS_PATH to non-existent file
        monkeypatch.setenv("CONVERTER_JS_PATH", "/nonexistent/converter.js")

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("shutil.which", return_value="/usr/local/bin/node"):
                state = {**base_state, "structure_json_path": str(structure_json)}
                result = convert_with_docxjs_node(state)

        assert result["conversion_success"] is False
        assert result["last_error"] == "converter.js not found"
        assert result["status"] == "error_handling"
        assert result["conversion_attempts"] == 1

    def test_subprocess_timeout(self, base_state, monkeypatch, tmp_path):
        """Test when conversion times out."""
        # Create mock structure.json
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        # Create mock converter.js at an absolute path
        converter_js = tmp_path / "converter.js"
        converter_js.write_text("// mock")

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            # Set CONVERTER_JS_PATH to the absolute path
            monkeypatch.setenv("CONVERTER_JS_PATH", str(converter_js))

            with patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired("node", 120)
            ):
                with patch("shutil.which", return_value="/usr/local/bin/node"):
                    state = {**base_state, "structure_json_path": str(structure_json)}
                    result = convert_with_docxjs_node(state)

        assert result["conversion_success"] is False
        assert "timeout" in result["last_error"].lower()
        assert result["status"] == "error_handling"
        assert result["conversion_attempts"] == 1

    def test_subprocess_nonzero_exit(self, base_state, monkeypatch, tmp_path):
        """Test when converter exits with non-zero code."""
        # Create mock structure.json
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        # Create mock converter.js that exists
        converter_js = tmp_path / "converter.js"
        converter_js.write_text("// mock")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: Invalid JSON structure"

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("subprocess.run", return_value=mock_result):
                with patch("shutil.which", return_value="/usr/local/bin/node"):
                    state = {
                        **base_state,
                        "structure_json_path": str(structure_json),
                        "conversion_attempts": 2,  # Already tried twice
                    }
                    result = convert_with_docxjs_node(state)

        assert result["conversion_success"] is False
        assert "Invalid JSON structure" in result["last_error"]
        assert result["status"] == "error_handling"
        assert result["conversion_attempts"] == 3  # Incremented

    def test_conversion_attempts_incremented(self, base_state, monkeypatch, tmp_path):
        """Test that conversion_attempts is incremented on each run."""
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        # Create mock converter.js
        converter_js = tmp_path / "converter.js"
        converter_js.write_text("// mock")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Created DOCX"
        mock_result.stderr = ""

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("subprocess.run", return_value=mock_result):
                with patch("shutil.which", return_value="/usr/local/bin/node"):
                    # Start with 5 attempts
                    state = {
                        **base_state,
                        "structure_json_path": str(structure_json),
                        "conversion_attempts": 5,
                    }
                    result = convert_with_docxjs_node(state)

        assert result["conversion_attempts"] == 6

    def test_timeout_from_env(self, base_state, monkeypatch, tmp_path):
        """Test that timeout is read from CONVERSION_TIMEOUT_SECONDS env var."""
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        # Create mock converter.js
        converter_js = tmp_path / "converter.js"
        converter_js.write_text("// mock")

        monkeypatch.setenv("CONVERSION_TIMEOUT_SECONDS", "300")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Created DOCX"
        mock_result.stderr = ""

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                with patch("shutil.which", return_value="/usr/local/bin/node"):
                    state = {**base_state, "structure_json_path": str(structure_json)}
                    convert_with_docxjs_node(state)

                # Verify timeout was 300
                call_kwargs = mock_run.call_args.kwargs
                assert call_kwargs["timeout"] == 300

    def test_node_path_env_override(self, base_state, monkeypatch, tmp_path):
        """Test that NODE_PATH env var is used when set."""
        structure_json = tmp_path / "structure.json"
        structure_json.write_text('{"sections": []}')

        # Create mock converter.js
        converter_js = tmp_path / "converter.js"
        converter_js.write_text("// mock")

        monkeypatch.setenv("NODE_PATH", "/custom/node/path")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Created DOCX"
        mock_result.stderr = ""

        with patch("backend.graph_nodes.SessionManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.get_path.return_value = tmp_path
            mock_sm.return_value = mock_instance

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                with patch("shutil.which", return_value="/usr/local/bin/node"):
                    state = {**base_state, "structure_json_path": str(structure_json)}
                    convert_with_docxjs_node(state)

                # Verify NODE_PATH was used
                call_args = mock_run.call_args.args[0]
                assert call_args[0] == "/custom/node/path"
