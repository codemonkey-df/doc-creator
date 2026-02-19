"""Pipeline module for document generation workflow."""

import logging
import re
import threading
from pathlib import Path

from src.llm.generator import ResolvedContext, generate_content
from src.llm.healer import heal_markdown, needs_healing
from src.scanner.ref_scanner import Ref, scan_files
from src.tui.state import AppState
from src.converter.run_converter import convert_to_docx
from src.config import LlmConfig
from src.resolver.ref_resolver import resolve_refs

# Re-export for backward compatibility
resolve_references = resolve_refs

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Exception raised when a pipeline stage fails."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        self.message = message
        super().__init__(f"[{stage}] {message}")


def validate_config(state: AppState) -> None:
    """Validate that the document configuration is complete.

    Args:
        state: The application state to validate.

    Raises:
        PipelineError: If validation fails.
    """
    if not state.title or state.title == "Untitled":
        raise PipelineError("validate", "Document title required")

    if not state.intro_file:
        raise PipelineError("validate", "Introduction file required")

    if not state.chapters:
        raise PipelineError("validate", "At least one chapter required")


def scan_references(state: AppState) -> list[Ref]:
    """Scan intro and chapter files for references.

    Args:
        state: The application state containing intro and chapters.

    Returns:
        List of Ref objects found in the files.
    """
    paths: list[Path] = []

    if state.intro_file:
        paths.append(Path(state.intro_file))

    for chapter in state.chapters:
        if chapter.file_path:
            paths.append(Path(chapter.file_path))

    return scan_files(paths)


def write_output(markdown: str, state: AppState) -> Path:
    """Write the generated markdown to an output file.

    Args:
        markdown: The generated markdown content.
        state: The application state.

    Returns:
        Path to the written output file.
    """
    # Create output directory if it doesn't exist
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Slugify the title
    title_slug = slugify(state.title)

    # Write the file
    output_path = output_dir / f"{title_slug}.md"
    output_path.write_text(markdown, encoding="utf-8")

    return output_path


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug.

    Args:
        text: The text to slugify.

    Returns:
        The slugified text.
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace spaces with dashes
    slug = slug.replace(" ", "-")
    # Remove non-alphanumeric characters (except dashes)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Remove multiple consecutive dashes
    slug = re.sub(r"-+", "-", slug)
    # Remove leading/trailing dashes
    slug = slug.strip("-")
    return slug


def run_pipeline(state: AppState) -> Path | None:
    """Run the complete document generation pipeline.

    Args:
        state: The application state containing document configuration.

    Returns:
        Path to the output .docx file, or None if pipeline failed.
    """
    try:
        # Initialize LLM config
        config = LlmConfig()

        # Stage 1: Validate configuration
        state.log_lines.append("Starting pipeline...")
        validate_config(state)

        # Stage 2: Scan references
        state.log_lines.append("Scanning references...")
        refs = scan_references(state)

        # Stage 3: Resolve references
        state.log_lines.append("Resolving references...")
        resolved = resolve_refs(refs, state)

        # Stage 4: Generate content
        state.log_lines.append("Generating content...")
        markdown = generate_content(state, resolved, config)

        # Stage 4b: Self-heal (after generate_content)
        if needs_healing(markdown):
            state.log_lines.append("Self-healing markdown...")
            markdown = heal_markdown(markdown, config)

        # Stage 5: Write output
        state.log_lines.append("Writing output...")
        output_path = write_output(markdown, state)

        # Stage 6: Convert to DOCX
        state.log_lines.append("Converting to DOCX...")
        docx_path = output_path.with_suffix(".docx")
        convert_to_docx(output_path, state.title, docx_path)

        state.log_lines.append(f"Done. Output: {docx_path}")
        logger.info("pipeline_complete", extra={"output_path": str(docx_path)})

        return docx_path

    except PipelineError as e:
        state.log_lines.append(f"Error [{e.stage}]: {e.message}")
        logger.error("pipeline_error", extra={"stage": e.stage, "error_msg": e.message})
        return None


def run_pipeline_in_background(state: AppState) -> None:
    """Run the pipeline in a background thread.

    Args:
        state: The application state.
    """
    thread = threading.Thread(target=run_pipeline, args=(state,))
    thread.start()
