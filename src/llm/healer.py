"""Self-heal module for fixing malformed Markdown."""

from src.llm.client import call_llm
from src.llm.prompts import prompt_self_heal
from src.config import LlmConfig


def needs_healing(markdown: str) -> bool:
    """Check if the markdown needs healing.

    Detects two types of issues:
    1. Unmatched code fences (odd number of ```)
    2. Headings without blank lines before them

    Args:
        markdown: The markdown content to check.

    Returns:
        True if the markdown has issues that need fixing, False otherwise.
    """
    # Check for unmatched code fences
    code_fence_count = markdown.count("```")
    if code_fence_count % 2 != 0:
        return True

    # Check for headings without blank lines before them
    lines = markdown.split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            # Check if previous line is not blank (skip first line)
            if i > 0 and lines[i - 1].strip() != "":
                return True

    return False


def heal_markdown(markdown: str, config: LlmConfig) -> str:
    """Call the LLM to fix malformed Markdown.

    Args:
        markdown: The potentially malformed Markdown content.

    Returns:
        The fixed Markdown content.
    """
    system, user = prompt_self_heal(markdown)
    return call_llm(system, user, config)
