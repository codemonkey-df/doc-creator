"""Content generator module for assembling final markdown documents."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.llm.client import call_llm
from src.llm.prompts import (
    prompt_structure_chapter,
    prompt_summarize_intro,
)
from src.scanner.ref_scanner import Ref
from src.tui.state import AppState
from src.config import LlmConfig

logger = logging.getLogger(__name__)


@dataclass
class ResolvedContext:
    """Context from reference resolution."""

    skipped: list[Ref] = field(default_factory=list)
    provided: list[Ref] = field(default_factory=list)
    to_summarize: list[tuple[str, str]] = field(default_factory=list)


def read_file(path: str | None) -> str:
    """Read content from a file path.

    Args:
        path: The file path to read. If None, returns empty string.

    Returns:
        The file content as a string. Returns empty string if file doesn't exist.
    """
    if path is None:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, IOError):
        return ""


def count_chapters_in_content(content: str) -> int:
    """Count the number of chapters in markdown content.

    Looks for ## Chapter N headings where N is a number.
    Returns the highest chapter number found (for offset calculation).

    Args:
        content: The markdown content to analyze.

    Returns:
        The highest chapter number found, or 0 if no chapters found.
    """
    # Match ## Chapter 1, ## Chapter 2, etc.
    pattern = r"^##\s+Chapter\s+(\d+)"
    matches = re.findall(pattern, content, re.MULTILINE)
    if not matches:
        return 0
    # Return the highest chapter number
    return max(int(m) for m in matches)


def generate_content(
    state: AppState, resolved: ResolvedContext, config: LlmConfig
) -> str:
    """Generate final markdown content from intro and chapter files.

    Args:
        state: The application state containing title, intro_file, and chapters.
        resolved: The resolved context containing to_summarize content.

    Returns:
        The assembled markdown document.
    """
    # Check if we're in imported workflow
    if state.imported_file:
        return generate_from_imported(state, resolved, config)

    # Normal workflow: summarize intro
    state.log_lines.append("Summarizing introduction...")
    intro_content = read_file(state.intro_file)

    logger.info("intro_source_loaded", extra={"intro_file": state.intro_file, "content_len": len(intro_content)})

    if not intro_content.strip():
        logger.warning("Intro source content is empty!")

    system, user = prompt_summarize_intro(intro_content)
    intro_md = call_llm(system, user, config, stage="intro")

    logger.info("intro_generated", extra={"intro_len": len(intro_md), "intro_preview": intro_md[:200] if intro_md else "EMPTY"})

    # Step 2: Structure each chapter
    chapter_mds = []

    for i, chapter in enumerate(state.chapters):
        title = chapter.custom_title or f"Chapter {i + 1}"

        # Read chapter content
        chapter_content = read_file(chapter.file_path)

        logger.info("chapter_source_loaded", extra={"chapter_file": chapter.file_path, "content_len": len(chapter_content)})

        if not chapter_content.strip():
            logger.warning(f"Chapter source content is empty: {chapter.file_path}")

        # Inject to_summarize content if applicable
        extra_context = ""
        for chap_path, summary_content in resolved.to_summarize:
            if chap_path == chapter.file_path:
                extra_context = (
                    f"\n\nAdditional context to consider:\n{summary_content}"
                )

        system, user = prompt_structure_chapter(chapter_content + extra_context, title)
        chapter_md = call_llm(system, user, config, stage=f"chapter_{i+1}")

        logger.info("chapter_generated", extra={"chapter": title, "chapter_len": len(chapter_md), "preview": chapter_md[:200] if chapter_md else "EMPTY"})

        chapter_mds.append(chapter_md)

    # Step 3: Assemble final output (title and TOC added by converter)
    output = f"{intro_md}\n\n" + "\n\n".join(chapter_mds)

    state.log_lines.append("Content generation complete.")
    logger.info("content_assembled", extra={"total_len": len(output)})
    return output


def generate_from_imported(
    state: AppState, resolved: ResolvedContext, config: LlmConfig
) -> str:
    """Generate content when importing an existing MD file.

    The imported file provides the base content, and additional chapters
    are processed and appended.

    Args:
        state: The application state containing imported_file and chapters.
        resolved: The resolved context containing to_summarize content.
        config: LLM configuration.

    Returns:
        The assembled markdown document.
    """
    # Read imported file
    state.log_lines.append("Reading imported file...")
    imported_content = read_file(state.imported_file)

    logger.info("imported_source_loaded", extra={"imported_file": state.imported_file, "content_len": len(imported_content)})

    if not imported_content.strip():
        logger.warning("Imported source content is empty!")

    # Count existing chapters in imported file to offset new chapter numbers
    chapter_offset = count_chapters_in_content(imported_content)

    # Process additional chapters (if any)
    chapter_mds = []

    for i, chapter in enumerate(state.chapters):
        # Offset chapter number by existing chapters in imported file
        chapter_number = chapter_offset + i + 1
        title = chapter.custom_title or f"Chapter {chapter_number}"

        # Read chapter content
        chapter_content = read_file(chapter.file_path)

        logger.info("chapter_source_loaded", extra={"chapter_file": chapter.file_path, "content_len": len(chapter_content)})

        if not chapter_content.strip():
            logger.warning(f"Chapter source content is empty: {chapter.file_path}")

        # Inject to_summarize content if applicable
        extra_context = ""
        for chap_path, summary_content in resolved.to_summarize:
            if chap_path == chapter.file_path:
                extra_context = (
                    f"\n\nAdditional context to consider:\n{summary_content}"
                )

        system, user = prompt_structure_chapter(chapter_content + extra_context, title)
        chapter_md = call_llm(system, user, config, stage=f"chapter_{chapter_number}")

        logger.info("chapter_generated", extra={"chapter": title, "chapter_len": len(chapter_md), "preview": chapter_md[:200] if chapter_md else "EMPTY"})

        chapter_mds.append(chapter_md)

    # Assemble: imported content + new chapters
    if chapter_mds:
        output = imported_content + "\n\n" + "\n\n".join(chapter_mds)
    else:
        output = imported_content

    state.log_lines.append("Content generation complete.")
    logger.info("content_assembled", extra={"total_len": len(output)})
    return output
