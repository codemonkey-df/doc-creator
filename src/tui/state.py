"""Application state dataclasses."""

from dataclasses import dataclass, field


@dataclass
class ChapterEntry:
    """Represents a chapter in the document."""

    file_path: str
    custom_title: str | None = None


@dataclass
class AppState:
    """Application state for DocForge."""

    title: str = "Untitled"
    intro_file: str | None = None
    chapters: list[str] = field(default_factory=list)
    detected_files: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
