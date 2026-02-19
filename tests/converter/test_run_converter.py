"""Tests for the DOCX converter wrapper."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.converter.run_converter import (
    ConverterError,
    _find_node_executable,
    _get_converter_script_path,
    convert_to_docx,
)


class TestFindNodeExecutable:
    """Tests for _find_node_executable function."""

    @patch("src.converter.run_converter.shutil.which")
    def test_finds_node_in_path(self, mock_which):
        """Test that node is found in PATH."""
        mock_which.return_value = "/usr/local/bin/node"
        result = _find_node_executable()
        assert result == "/usr/local/bin/node"

    @patch("src.converter.run_converter.shutil.which")
    def test_uses_node_path_env_var(self, mock_which):
        """Test that NODE_PATH env var is respected."""
        with patch.dict(os.environ, {"NODE_PATH": "/custom/node"}):
            mock_which.return_value = "/custom/node"
            result = _find_node_executable()
            assert result == "/custom/node"

    @patch("src.converter.run_converter.shutil.which")
    def test_prefers_node_path_env_var_over_which(self, mock_which):
        """Test that NODE_PATH takes precedence over which()."""
        with patch.dict(os.environ, {"NODE_PATH": "/custom/node"}):
            mock_which.return_value = "/usr/bin/node"
            result = _find_node_executable()
            assert result == "/custom/node"

    @patch("src.converter.run_converter.shutil.which")
    def test_raises_when_node_not_found(self, mock_which):
        """Test that ConverterError is raised when node is not found."""
        mock_which.return_value = None
        with pytest.raises(ConverterError) as exc_info:
            _find_node_executable()
        assert "Node.js is not installed" in str(exc_info.value)


class TestGetConverterScriptPath:
    """Tests for _get_converter_script_path function."""

    def test_returns_path_to_converter_script(self):
        """Test that the correct path to converter/convert.js is returned."""
        result = _get_converter_script_path()
        # Should resolve to converter/convert.js in project root
        assert result.name == "convert.js"
        assert result.parent.name == "converter"


class TestConvertToDocx:
    """Tests for convert_to_docx function."""

    @patch("src.converter.run_converter._find_node_executable")
    @patch("src.converter.run_converter._get_converter_script_path")
    @patch("src.converter.run_converter.subprocess.run")
    def test_converts_successfully(self, mock_run, mock_script_path, mock_find_node):
        """Test successful conversion."""
        # Setup mocks
        mock_find_node.return_value = "/usr/bin/node"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_script_path.return_value = mock_path

        markdown_path = Path("/tmp/test.md")
        output_path = Path("/tmp/test.docx")

        # Mock successful subprocess result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Execute
        result = convert_to_docx(markdown_path, "Test Title", output_path)

        # Verify
        assert result == output_path
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "/usr/bin/node" in call_args

    @patch("src.converter.run_converter._find_node_executable")
    @patch("src.converter.run_converter._get_converter_script_path")
    @patch("src.converter.run_converter.subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_run, mock_script_path, mock_find_node):
        """Test that ConverterError is raised on non-zero exit code."""
        # Setup mocks
        mock_find_node.return_value = "/usr/bin/node"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_script_path.return_value = mock_path

        markdown_path = Path("/tmp/test.md")
        output_path = Path("/tmp/test.docx")

        # Mock failed subprocess result
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Conversion failed: invalid markdown"
        mock_run.return_value = mock_result

        # Execute and verify
        with pytest.raises(ConverterError) as exc_info:
            convert_to_docx(markdown_path, "Test Title", output_path)

        assert "Conversion failed" in str(exc_info.value)

    @patch("src.converter.run_converter._find_node_executable")
    @patch("src.converter.run_converter._get_converter_script_path")
    def test_raises_when_script_missing(self, mock_script_path, mock_find_node):
        """Test that ConverterError is raised when converter script is missing."""
        # Setup mocks
        mock_find_node.return_value = "/usr/bin/node"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_script_path.return_value = mock_path

        markdown_path = Path("/tmp/test.md")
        output_path = Path("/tmp/test.docx")

        # Execute and verify
        with pytest.raises(ConverterError) as exc_info:
            convert_to_docx(markdown_path, "Test Title", output_path)

        assert "not found" in str(exc_info.value).lower()

    @patch("src.converter.run_converter._find_node_executable")
    @patch("src.converter.run_converter._get_converter_script_path")
    @patch("src.converter.run_converter.subprocess.run")
    def test_raises_on_subprocess_timeout(
        self, mock_run, mock_script_path, mock_find_node
    ):
        """Test that ConverterError is raised on subprocess timeout."""
        # Setup mocks
        mock_find_node.return_value = "/usr/bin/node"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_script_path.return_value = mock_path

        markdown_path = Path("/tmp/test.md")
        output_path = Path("/tmp/test.docx")

        # Mock timeout
        mock_run.side_effect = TimeoutError("Conversion timed out")

        # Execute and verify
        with pytest.raises(ConverterError):
            convert_to_docx(markdown_path, "Test Title", output_path)
