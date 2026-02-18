"""Tests for FileWatcher class."""

import tempfile
import threading
import time
from pathlib import Path


from src.tui.watcher import FileWatcher


class TestFileWatcher:
    """Test suite for FileWatcher class."""

    def test_scan_files_returns_markdown_files(self):
        """Test that scan returns sorted markdown files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir)

            # Create test files
            (input_path / "z_file.md").touch()
            (input_path / "a_file.md").touch()
            (input_path / "b_file.md").touch()
            (input_path / "ignore.txt").touch()

            callback_called = threading.Event()
            detected = []

            def callback(files):
                nonlocal detected
                detected = files
                callback_called.set()

            watcher = FileWatcher(input_path, callback)
            files = watcher._scan_files()

            assert files == ["a_file.md", "b_file.md", "z_file.md"]

    def test_scan_files_empty_directory(self):
        """Test that empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir)

            watcher = FileWatcher(input_path, lambda f: None)
            files = watcher._scan_files()

            assert files == []

    def test_scan_files_nonexistent_directory(self):
        """Test that nonexistent directory returns empty list."""
        input_path = Path("/nonexistent/path/12345")

        watcher = FileWatcher(input_path, lambda f: None)
        files = watcher._scan_files()

        assert files == []

    def test_file_created_event_triggers_callback(self):
        """Test that creating a .md file triggers callback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir)

            callback_called = threading.Event()
            detected_files = []

            def callback(files):
                nonlocal detected_files
                detected_files = files
                callback_called.set()

            watcher = FileWatcher(input_path, callback)
            watcher.start()

            try:
                # Wait a bit for watcher to start
                time.sleep(0.2)

                # Create a markdown file
                (input_path / "new_file.md").touch()

                # Wait for callback (max 2 seconds)
                assert callback_called.wait(timeout=2), "Callback was not triggered"

                assert "new_file.md" in detected_files
            finally:
                watcher.stop()

    def test_file_deleted_event_triggers_callback(self):
        """Test that deleting a .md file triggers callback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir)

            # Pre-create a file
            test_file = input_path / "to_delete.md"
            test_file.touch()

            callback_called = threading.Event()
            detected_files = []

            def callback(files):
                nonlocal detected_files
                detected_files = files
                callback_called.set()

            watcher = FileWatcher(input_path, callback)
            watcher.start()

            try:
                # Wait a bit for watcher to start
                time.sleep(0.2)

                # Delete the file
                test_file.unlink()

                # Wait for callback (max 2 seconds)
                assert callback_called.wait(timeout=2), "Callback was not triggered"

                # Give filesystem time to settle
                time.sleep(0.3)

                assert "to_delete.md" not in detected_files
            finally:
                watcher.stop()

    def test_stable_numeric_ids(self):
        """Test that files are sorted by filename for stable IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir)

            # Create files in unsorted order
            (input_path / "chapters.md").touch()
            (input_path / "01_intro.md").touch()
            (input_path / "02_chapter1.md").touch()

            watcher = FileWatcher(input_path, lambda f: None)
            files = watcher._scan_files()

            # Should be alphabetically sorted
            assert files == ["01_intro.md", "02_chapter1.md", "chapters.md"]

    def test_watcher_starts_and_stops(self):
        """Test that watcher starts and stops cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir)

            watcher = FileWatcher(input_path, lambda f: None)
            watcher.start()

            # Wait for watcher to start
            time.sleep(0.2)

            # Verify observer is running
            assert watcher._observer.is_alive()

            watcher.stop()

            # Give time for observer to stop
            time.sleep(0.2)

            # Verify observer is stopped
            assert not watcher._observer.is_alive()

    def test_non_markdown_files_ignored(self):
        """Test that non-markdown files are not included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir)

            # Create various file types
            (input_path / "document.md").touch()
            (input_path / "readme.txt").touch()
            (input_path / "data.json").touch()

            watcher = FileWatcher(input_path, lambda f: None)
            files = watcher._scan_files()

            assert files == ["document.md"]
            assert "readme.txt" not in files
            assert "data.json" not in files
