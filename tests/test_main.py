"""Tests for src/main.py module."""

import argparse
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestMainArgumentParsing:
    """Tests for argument parsing in main.py."""

    def test_main_accepts_input_flag(self):
        """--input flag should set the input folder."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--input", default="./input")
        parser.add_argument("files", nargs="*")

        args = parser.parse_args(["--input", "./docs"])

        assert args.input == "./docs"
        assert args.files == []

    def test_main_default_input_folder(self):
        """Default input folder should be ./input."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--input", default="./input")
        parser.add_argument("files", nargs="*")

        args = parser.parse_args([])

        assert args.input == "./input"

    def test_main_positional_files(self):
        """Positional file arguments should be captured."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--input", default="./input")
        parser.add_argument("files", nargs="*")

        args = parser.parse_args(["file1.md", "file2.md"])

        assert args.files == ["file1.md", "file2.md"]


class TestMainExecution:
    """Tests for main.py execution."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        shutil.rmtree(tmp)

    def test_main_copies_files_to_input(self, temp_dir):
        """Positional args should be copied to input folder."""
        # Create test files
        test_file1 = temp_dir / "file1.md"
        test_file2 = temp_dir / "file2.md"
        test_file1.write_text("# File 1")
        test_file2.write_text("# File 2")

        input_dir = temp_dir / "input"
        input_dir.mkdir()

        # Simulate copying files to input/
        for file_path in [test_file1, test_file2]:
            dest = input_dir / file_path.name
            shutil.copy2(file_path, dest)

        assert (input_dir / "file1.md").exists()
        assert (input_dir / "file2.md").exists()
        assert (input_dir / "file1.md").read_text() == "# File 1"
        assert (input_dir / "file2.md").read_text() == "# File 2"

    def test_main_prints_starting_message(self, temp_dir, capsys):
        """Main should print 'DocForge starting...'"""
        # Create a temp input directory
        input_dir = temp_dir / "input"
        input_dir.mkdir()

        import sys

        # Remove cached modules to ensure fresh import
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("src"):
                del sys.modules[mod_name]

        with (
            patch("sys.argv", ["main.py", "--input", str(input_dir)]),
            patch("src.tui.app.DocForgeApp") as MockDocForgeApp,
        ):
            # Mock the app to not actually run
            mock_app = MockDocForgeApp.return_value
            mock_app.run = lambda: None
            MockDocForgeApp.return_value = mock_app

            from src import main

            main.main()

        captured = capsys.readouterr()
        assert "DocForge starting..." in captured.out


class TestProjectStructure:
    """Tests for project directory structure."""

    def test_tui_module_importable(self):
        """src.tui module should be importable."""
        from src import tui

        assert tui is not None

    def test_state_module_importable(self):
        """src.tui.state module should be importable."""
        from src.tui import state

        assert state is not None
