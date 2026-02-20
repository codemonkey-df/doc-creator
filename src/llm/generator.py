"""Content generator module for assembling final markdown documents."""

import logging
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
    # Step 1: Summarize intro
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
