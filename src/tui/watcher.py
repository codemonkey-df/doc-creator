"""File watcher for monitoring input folder changes."""

import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class MarkdownFileHandler(FileSystemEventHandler):
    """Handler for markdown file system events."""

    def __init__(self, callback: Callable[[str, str], None]):
        self.callback = callback

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self.callback("created", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self.callback("deleted", event.src_path)


class FileWatcher:
    """Watches input folder for markdown file changes."""

    def __init__(self, input_path: Path, callback: Callable[[list[str]], None]):
        self.input_path = input_path
        self.callback = callback
        self._observer = Observer()
        self._handler = MarkdownFileHandler(self._handle_event)
        self._thread: threading.Thread | None = None

    def _handle_event(self, event_type: str, file_path: str):
        """Handle file system events and refresh file list."""
        # Small delay to let filesystem settle after events
        time.sleep(0.1)
        files = self._scan_files()
        self.callback(files)

    def _scan_files(self) -> list[str]:
        """Scan input folder for markdown files, sorted by filename."""
        if not self.input_path.exists():
            return []
        return sorted([f.name for f in self.input_path.glob("*.md")])

    def start(self):
        """Start watching the input folder in a daemon thread."""
        self._observer.schedule(self._handler, str(self.input_path), recursive=False)
        self._observer.start()

    def stop(self):
        """Stop the file watcher."""
        self._observer.stop()
        self._observer.join()
