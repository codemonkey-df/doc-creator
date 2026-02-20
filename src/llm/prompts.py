"""Prompt templates for document generation pipeline."""


def prompt_summarize_intro(content: str) -> tuple[str, str]:
    """Generate a prompt to summarize/introduce a document from source content.

    Args:
        content: The source content to summarize.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = (
        "You are a technical writer. Create a concise, professional introduction. "
        "Focus on the main purpose and scope. Keep it brief - 2-4 paragraphs maximum."
    )
    user = f"""Create a brief introduction for a document based on this content:

---
{content}
---

Write a 4-6 paragraph introduction that:
- Summarizes the document's purpose
- Outlines what the reader will learn
- Uses formal but accessible tone

Return only valid Markdown. Start with H2 heading "Introduction"."""
    return (system, user)


def prompt_structure_chapter(content: str, title: str) -> tuple[str, str]:
    """Generate a prompt to structure a chapter from source content.

    Args:
        content: The source content for the chapter.
        title: The title of the chapter.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = (
        "You are a technical writer. Create a well-structured, condensed chapter. "
        "Summarize long content, keep key details. Use clear heading hierarchy."
    )
    user = f"""Transform this content into a professional chapter titled "{title}":

---
{content}
---

Requirements:
- Start with H2 heading: ## {title}
- Add a brief description (2-3 sentences)
- Use H3 for major sections only (skip minor details)
- For lists/tasks, keep only the key items (top 3-5)
- Skip repetitive details and internal notes
- Keep code blocks only if critical
- Total chapter should be 30-50% of original length

Return only valid Markdown chapter content."""
    return (system, user)


def prompt_generate_toc(
    doc_title: str,
    chapter_list: list[tuple[str, list[str]]]
) -> tuple[str, str]:
    """Generate a prompt to create a table of contents.

    Args:
        doc_title: The document title.
        chapter_list: List of tuples of (chapter_title, subheadings_list).

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = (
        "You are a technical writer. Generate a clean, professional table of contents. "
        "List only major sections - skip detailed sub-items."
    )

    chapters_md = []
    for title, subheadings in chapter_list:
        # Filter out Stories - only keep major EPICs/topics
        major_subheadings = [s for s in subheadings if not s.lower().startswith("story")]
        if major_subheadings:
            chapters_md.append(f"- {title}")
            for sub in major_subheadings[:3]:  # Limit to 3 subheadings max
                chapters_md.append(f"  - {sub}")
        else:
            chapters_md.append(f"- {title}")

    chapters_str = "\n".join(chapters_md)

    user = f"""Create a table of contents for "{doc_title}" with this structure:

{chapters_str}

IMPORTANT:
- Only include major section headings (EPICs, Overview, etc.)
- EXCLUDE Stories (e.g., "Story 1.1") from TOC
- Limit to 3 subheadings per chapter maximum
- Include an "Introduction" entry

Format as a clean Markdown list with 2-space indentation for sub-items."""
    return (system, user)


def prompt_self_heal(markdown: str) -> tuple[str, str]:
    """Generate a prompt to fix/heal malformed Markdown.

    Args:
        markdown: The potentially malformed Markdown content.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = "You are a Markdown expert. Fix any malformed Markdown."
    user = f"""Fix any issues in the following Markdown content:

{markdown}

Return only valid, corrected Markdown. Do not add any explanatory text."""
    return (system, user)


def prompt_summarize_external(content: str, context: str) -> tuple[str, str]:
    """Generate a prompt to summarize an external file for injection into a chapter.

    Args:
        content: The content of the external file to summarize.
        context: The chapter or document context this summary will be injected into.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = "You are a technical writer. Summarize external content concisely."
    user = f"""Summarize the following external content for inclusion in a chapter about "{context}".

Focus on extracting the key information that would be relevant to include in this chapter.
Keep the summary concise but informative. Return the summary in a format suitable for
injecting as additional context.

External content:
---
{content}
---

Return only the summary, no introductory text."""
    return (system, user)
