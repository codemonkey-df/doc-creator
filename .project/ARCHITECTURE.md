# DocForge — Architecture & Implementation Guide

> A Claude Code-style TUI for generating structured DOCX documents from Markdown files using LLM-powered summarization.

---

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                    DocForge TUI                         │
│  (rich-based, slash-command driven, Claude Code style)  │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │    Config Phase     │  /title, /intro, /chapter, /forge
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Reference Scan    │  regex on selected .md files
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  Reference Resolve  │  ask user: skip | provide | read
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   LLM Generation    │  LiteLLM → summarize, structure, TOC
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   DOCX Conversion   │  Node.js docx library via subprocess
    └──────────┬──────────┘
               │
            output.docx
```

---

## Directory Structure

```
docforge/
├── main.py                    # Entry point — launches TUI
├── pyproject.toml             # UV project config
│
├── src/
│   ├── tui/
│   │   ├── app.py             # Main TUI App (rich Live + Layout)
│   │   ├── panels.py          # Sources panel, Outline panel, Log panel
│   │   ├── commands.py        # Slash command parser + handlers
│   │   └── state.py           # AppState dataclass (title, intro, chapters)
│   │
│   ├── scanner/
│   │   └── ref_scanner.py     # Regex-based reference scanner
│   │
│   ├── resolver/
│   │   └── ref_resolver.py    # Interactive reference resolution logic
│   │
│   ├── llm/
│   │   ├── client.py          # LiteLLM wrapper
│   │   └── prompts.py         # All prompt templates
│   │
│   ├── pipeline/
│   │   └── pipeline.py        # Sequential pipeline: validate→scan→resolve→generate→convert
│   │
│   └── converter/
│       └── run_converter.py   # subprocess wrapper for Node.js
│
├── converter/
│   ├── package.json
│   ├── convert.js             # Markdown → DOCX via docx npm library
│   └── md_parser.js           # Custom MD → docx-js AST parser
│
└── input/                     # Default input folder (user drops .md files here)
```

---

## Component Design

### 1. TUI App (`src/tui/app.py`)

Built with `rich.live.Live` + `rich.layout.Layout`. Two-panel layout:

```
┌──────────────────────────────────────────────────┐
│  DocForge v1.0              session: abc123       │ ← Header
├────────────────────┬─────────────────────────────┤
│  DETECTED SOURCES  │  DOCUMENT OUTLINE           │
│  [1] intro.md      │  Title:   Untitled           │
│  [2] chapter1.md ✓ │  Intro:   (none)             │
│  [3] chapter2.md ✓ │  Ch 1:    chapter1.md        │
│                    │  Ch 2:    chapter2.md        │
├────────────────────┴─────────────────────────────┤
│  LOG                                              │
│  > Scanned 3 files. 2 image refs found.          │
├───────────────────────────────────────────────────┤
│  > /                                              │ ← Command prompt
└───────────────────────────────────────────────────┘
```

**AppState dataclass:**
```python
@dataclass
class AppState:
    title: str = "Untitled"
    intro_file: Path | None = None
    chapters: list[ChapterEntry] = field(default_factory=list)
    detected_files: list[Path] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)

@dataclass
class ChapterEntry:
    path: Path
    custom_title: str | None = None
```

### 2. Slash Commands (`src/tui/commands.py`)

| Command | Description |
|---------|-------------|
| `/title "My Doc"` | Set document title |
| `/intro 1` | Assign file [1] as introduction |
| `/chapter 2` | Add file [2] as next chapter |
| `/chapter 2 "Custom Title"` | Add with custom chapter name |
| `/remove 1` | Remove chapter at index 1 |
| `/reset` | Clear all mappings |
| `/forge` | Trigger the pipeline |
| `/help` | Show command list |
| `/quit` | Exit |

Parser handles quoted strings, numeric IDs, partial filename matching.

### 3. Reference Scanner (`src/scanner/ref_scanner.py`)

Pure regex, no external deps:

```python
PATTERNS = {
    "image":    re.compile(r'!\[([^\]]*)\]\(([^)]+)\)'),
    "path_ref": re.compile(r'(?<!!)\[([^\]]*)\]\(([^)#\s]+)\)'),
    "url":      re.compile(r'https?://[^\s\)\"]+'),
}

@dataclass
class Ref:
    type: Literal["image", "path", "url"]
    original: str
    resolved_path: Path | None
    status: Literal["found", "missing", "external"]
    source_file: Path
    line_number: int
```

Scan all intro + chapter files, return `list[Ref]`.

### 4. Reference Resolver (`src/resolver/ref_resolver.py`)

After scanning, present each unique ref and ask user:

```
REFERENCES FOUND (3)
─────────────────────────────────────────────────────
[1] IMAGE   diagram.png         → missing
    (a) Skip — insert [Image: diagram.png]
    (b) Provide path
    (c) Already in folder (auto-resolved)

[2] URL     https://github.com/x → external
    (a) Skip — insert [External URL]
    (b) Fetch & summarize (pass to LLM)

[3] PATH    ./api-spec.md       → missing
    (a) Skip — insert placeholder
    (b) Provide path
    (c) Read & summarize via LLM

> Choice for [1]: a
> Batch skip all images? [y/N]:
```

Resolution results are stored in `AppState` and passed to LLM context.

### 5. LLM Client (`src/llm/client.py`)

Thin wrapper around LiteLLM:

```python
from litellm import completion

def call_llm(system: str, user: str, model: str = "gpt-4o") -> str:
    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return response.choices[0].message.content
```

**Three LLM tasks (separate calls, simple prompts):**

| Task | Input | Output |
|------|-------|--------|
| Summarize intro | intro file content | Markdown summary with code/graphs preserved |
| Structure chapter | chapter file content + optional title | Structured markdown: heading, description, subchapters |
| Generate TOC | list of chapter titles + subheadings | Formatted `## Table of Contents` block |
| Self-heal | broken markdown snippet | Fixed markdown |

### 6. Pipeline (`src/pipeline/pipeline.py`)

Simple sequential Python functions, no framework:

```python
def run_pipeline(state: AppState, config: Config) -> Path:
    validate_config(state)              # raises if missing title/intro/chapters
    refs = scan_references(state)       # returns list[Ref]
    resolved = resolve_references(refs, state)  # interactive, updates state
    markdown = generate_content(state, resolved, config)  # LLM calls
    markdown = self_heal_if_needed(markdown)   # optional LLM pass
    docx_path = convert_to_docx(markdown, state.title)  # Node.js subprocess
    return docx_path
```

Each function has clear input/output. Errors raise `PipelineError` with stage name + message.

### 7. DOCX Converter (`converter/convert.js`)

Node.js script called via subprocess. Receives:
- `temp_output.md` — the generated markdown
- `--title "My Doc"` — document title for title page

Produces `output.docx`.

**Document structure it builds:**
1. Title page — centered, large font, `HeadingLevel.TITLE`
2. TOC page — `TableOfContents` element (auto-updates in Word)
3. Introduction section — `Heading1: "Introduction"`
4. Chapter sections — `Heading1: chapter title`, `Heading2` for subchapters

**Markdown elements it handles:**
| Markdown | DOCX Element |
|----------|-------------|
| `# H1` | `HeadingLevel.HEADING_1` |
| `## H2` | `HeadingLevel.HEADING_2` |
| `### H3` | `HeadingLevel.HEADING_3` |
| `` ```code``` `` | monospace `TextRun` with shaded background |
| `> blockquote` | indented paragraph |
| `- list` | `LevelFormat.BULLET` numbered config |
| `1. list` | `LevelFormat.DECIMAL` numbered config |
| `| table |` | `Table` with `WidthType.DXA` |
| `[Image: x]` | placeholder paragraph: *[Image: x]* italicized |
| `[External: x]` | placeholder paragraph: *[External: x]* |

---

## Data Flow

```
User selects files
      │
      ▼
AppState { title, intro_file, chapters[] }
      │
      ▼  /forge triggered
ref_scanner.scan(intro + chapters)
      │
      ▼
list[Ref] { type, path, status }
      │
      ▼  User makes choices
ResolvedContext { skipped[], provided[], to_summarize[] }
      │
      ▼  LLM calls
1. summarize_intro(intro_content) → intro_md
2. for ch in chapters:
     structure_chapter(ch_content, title) → ch_md
3. generate_toc(chapter_structures) → toc_md
      │
      ▼
temp_output.md = title_block + toc_md + intro_md + chapters_md
      │
      ▼  subprocess
node converter/convert.js temp_output.md --title "..." → output.docx
```

---

## LLM Prompts

### Intro Summary
```
System: You are a technical documentation writer. 
        Preserve all code snippets, tables, and diagrams (as ASCII/Mermaid).
        Return only valid Markdown.

User:   Summarize this introduction document into a clear, 
        professional introduction section.
        Keep: code blocks, graphs, important technical details.
        Remove: redundant headers, internal notes.
        
        --- DOCUMENT ---
        {content}
```

### Chapter Structuring
```
System: You are a technical documentation writer.
        Return only valid Markdown with proper heading hierarchy.

User:   Structure this file as a book chapter titled "{chapter_title}".
        Output format:
        ## {chapter_title}
        Brief chapter description (2-3 sentences)
        ### Subchapter 1
        ...content...
        
        Preserve: code blocks (```lang), tables, lists, diagrams.
        
        --- FILE CONTENT ---
        {content}
```

### TOC Generation
```
System: You are a technical documentation writer.

User:   Generate a Table of Contents for a document with this structure:
        Title: {title}
        Introduction: yes
        Chapters: {chapter_list}
        
        Format:
        ## Table of Contents
        1. Introduction
        2. {Chapter 1 title}
           2.1 {Subchapter}
        ...
```

### Self-Heal
```
System: You are a Markdown validator and fixer.

User:   Fix any Markdown formatting issues in this document.
        Rules: 
        - Headings must have a blank line before/after
        - Code blocks must have matching ``` delimiters  
        - Lists must be consistently indented
        Return ONLY the fixed Markdown, no explanations.
        
        --- BROKEN MARKDOWN ---
        {markdown}
```

---

## Implementation Phases

### Phase 1 — Core TUI (2–3 days)
- `main.py` entry point with `--input` arg
- `AppState` + `rich.live.Live` layout
- File detection from input folder
- `/title`, `/intro`, `/chapter`, `/reset`, `/help` commands
- Basic log panel

### Phase 2 — Reference Scanner (1 day)
- `ref_scanner.py` with 3 regex patterns
- Classification: found / missing / external
- Unit tests with fixture `.md` files

### Phase 3 — LLM + Pipeline (2 days)
- `client.py` with LiteLLM
- 3 prompt templates in `prompts.py`
- `pipeline.py` sequential runner
- Self-heal pass

### Phase 4 — DOCX Converter (2 days)
- `converter/convert.js` with `docx` npm package
- Handle all markdown elements
- Title page + TOC + sections
- `run_converter.py` subprocess wrapper

### Phase 5 — Reference Resolution UI (1 day)
- Interactive resolution screen in TUI
- Skip / provide / summarize actions
- Batch skip support

---

## Key Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "rich>=13.0",
    "watchdog>=4.0",
    "litellm>=1.40",
    "pydantic>=2.0",
]
```

```json
// converter/package.json
{
  "dependencies": {
    "docx": "^8.0.0"
  }
}
```

---

## Running the App

```bash
# Install Python deps
uv sync

# Install Node deps
cd converter && npm install

# Run with default input/ folder
uv run main.py

# Run with custom folder
uv run main.py --input /path/to/my/docs

# Run with files directly
uv run main.py file1.md file2.md file3.md
```

**Typical session:**
```
> /title "API Reference Guide"
> /intro 1          # intro.md
> /chapter 2        # auth.md
> /chapter 3 "Data Models"   # models.md  
> /forge
  → Scanning references... 3 found
  → [image] diagram.png — skip? (y): y
  → [url] https://github.com/x — skip? (y): y
  → Summarizing introduction...
  → Structuring chapter 1...
  → Structuring chapter 2...
  → Generating TOC...
  → Converting to DOCX...
  ✓ Output: output/API_Reference_Guide.docx
```

---

## Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| TUI framework | `rich` | Best-in-class terminal rendering, no heavy deps |
| File watching | `watchdog` | Cross-platform, reliable, simple API |
| LLM client | `litellm` | Model-agnostic, swap providers easily |
| Pipeline | Plain Python functions | No framework needed; simple to test and debug |
| DOCX generation | Node.js `docx` | Most capable library for `.docx` structure |
| No LangGraph | ✓ removed | Unnecessary complexity for a linear pipeline |
| No database | ✓ none | Session state is in-memory; config saved as JSON on demand |
