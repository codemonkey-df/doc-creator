"""Prompt templates for document generation pipeline."""


def prompt_summarize_intro(content: str) -> tuple[str, str]:
    """Generate a prompt to summarize/introduce a document from source content.

    Args:
        content: The source content to summarize.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = (
        "You are a technical writer. Generate a concise introduction for a document."
    )
    user = f"""Based on the following source content, generate a concise introduction:

{content}

Return only valid Markdown for the introduction."""
    return (system, user)


def prompt_structure_chapter(content: str, title: str) -> tuple[str, str]:
    """Generate a prompt to structure a chapter from source content.

    Args:
        content: The source content for the chapter.
        title: The title of the chapter.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = "You are a technical writer. Structure content into a well-formed chapter."
    user = f"""Using the following source content, create a well-structured chapter titled "{title}":

{content}

Return only valid Markdown for the chapter."""
    return (system, user)


def prompt_generate_toc(doc_title: str, chapter_list: list[str]) -> tuple[str, str]:
    """Generate a prompt to create a table of contents.

    Args:
        doc_title: The document title.
        chapter_list: List of chapter titles.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = "You are a technical writer. Generate a table of contents."
    chapters = "\n".join(f"- {title}" for title in chapter_list)
    user = f"""Create a table of contents for a document titled "{doc_title}" with the following chapters:

{chapters}

Return only valid Markdown for the table of contents."""
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
