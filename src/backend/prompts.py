"""Agent system and user prompts (Story 2.3). ARCHITECTURE §4.3.

System prompt enforces structure (Chapters → Sections → Subsections),
fidelity (code/logs verbatim), context (read current document before appending),
and when to interrupt (missing external file — ask user). User prompt template
includes current file, chapter, session, and validation_issues when present.
"""

from __future__ import annotations

import json
from typing import Any

# Single maintainable constant per AC2.3.2; content from ARCHITECTURE §4.3 (lines 298–339).
SYSTEM_PROMPT = """You are a professional document generation agent. Your task is to create 
structured Word documents from user-provided text files.

CRITICAL RULES:
1. PRESERVE FIDELITY (FC004): Copy code/logs verbatim in ```language blocks
2. STRUCTURE CONTENT (FC002): Use heading hierarchy # → ## → ###
3. TRACK CONTEXT (FC003): Always read temp file before adding new content
4. NO SUMMARIZATION: Technical content must be copied exactly
5. ASK FOR HELP (FC006): If you see reference to missing file, STOP and ask

WORKFLOW:
1. Call read_file(filename) to get source content
2. Call read_generated_file(lines=100) to see what's already written
3. Determine chapter/section structure
4. Call append_to_markdown(content) with new structured content
5. Call create_checkpoint(label) after each major section
6. If you encounter external reference: INTERRUPT and ask user

FORMATTING GUIDELINES:
- Use # for chapter titles (H1)
- Use ## for main sections (H2)
- Use ### for subsections (H3)
- Wrap ALL code in ```language fences
- Wrap ALL logs in ```text fences
- Use **bold** for emphasis, *italic* for subtle emphasis
- Create tables with proper markdown syntax

ASSET HANDLING (FC014, Story 3.3):
When you reference an image in your work or need to include one:
- Use the copy_image(source_path) tool to copy the file to session assets/
- Use the returned path in your markdown (e.g., ![My Diagram](./assets/diagram.png))
- If the file is missing, copy_image returns **[Image Missing: filename.png]** (visible in output)
- Always use the exact path returned by copy_image; do not modify it
Example:
  1. Call copy_image(source_path="./diagram.png")
  2. Response: "./assets/diagram.png"
  3. Use in markdown: ![Architecture Diagram](./assets/diagram.png)

EXAMPLE OUTPUT:
# Chapter 1: System Logs Analysis

## Server Startup Sequence

The following logs show the initialization process:

```text
[2025-01-15 08:00:01] INFO: Server starting...
[2025-01-15 08:00:02] INFO: Loading configuration...
[2025-01-15 08:00:03] INFO: Database connected
```

## Configuration Details

The server uses the following settings:

```json
{
  "port": 8080,
  "timeout": 30
}
```
"""


def build_user_prompt(state: dict[str, Any]) -> str:
    """Build the user prompt for this agent step from workflow state.

    Includes current file, chapter, session id, and instructions to use tools.
    When state has validation_issues (returning from validate_md), injects them
    so the agent can fix (AC2.3.4, Task 12).

    Args:
        state: DocumentState-like dict with session_id, input_files,
            current_file_index, current_chapter; optionally validation_issues.

    Returns:
        User prompt string.
    """
    session_id = state.get("session_id", "")
    input_files = state.get("input_files") or []
    current_file_index = state.get("current_file_index", 0)
    current_chapter = state.get("current_chapter", 0)
    current_file = (
        input_files[current_file_index]
        if 0 <= current_file_index < len(input_files)
        else (input_files[0] if input_files else "unknown")
    )

    lines = [
        f"You are processing file: {current_file}",
        f"Chapter: {current_chapter}",
        f"Session: {session_id}",
        "",
        "Your tasks:",
        f"1. Call read_file('{current_file}') to get content",
        "2. Call read_generated_file(lines=100) to see what's already written",
        "3. Structure content into chapters with proper headings (# → ## → ###)",
        "4. Call append_to_markdown(content) to add new content",
        "5. Call create_checkpoint(label) after each major section",
        "6. If you see an external or missing file reference, STOP and ask the user.",
        "",
        "Remember: Preserve all code/logs verbatim in ``` blocks. No summarization.",
    ]

    validation_issues = state.get("validation_issues")
    if validation_issues:
        lines.append("")
        lines.append("Validation issues to fix (from markdown lint):")
        if isinstance(validation_issues, list):
            for issue in validation_issues:
                if isinstance(issue, dict):
                    lines.append(f"  - {json.dumps(issue)}")
                else:
                    lines.append(f"  - {issue}")
        else:
            lines.append(f"  {validation_issues}")
        lines.append(
            "Fix the above issues using edit_markdown_line or append_to_markdown as needed."
        )

    return "\n".join(lines)
