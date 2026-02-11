# Epic 5: DOCX Conversion & Output Quality

## Brief Description

Convert validated markdown to DOCX via an intermediate JSON schema and docx-js, and verify output quality (headings, images, code, tables).

## Business Value

- Delivers the actual artifact users need (DOCX).
- Quality checks ensure headings, code blocks, tables, and images meet standards.

## Acceptance Criteria

- **FC002 (output):** Intermediate markdown produced and then converted (no direct MD→DOCX without structure).
- **FC011:** Post-generation checks for heading hierarchy, image rendering, code block formatting, table structure.
- Markdown → JSON schema (metadata + sections: heading1–3, paragraph, code_block, table, image).
- docx-js (Node subprocess) produces DOCX from JSON; Python invokes it and handles timeouts/errors.

## High-Level Stories (5)

1. Design and document JSON schema for docx-js (metadata, section types, image paths).
2. Implement MD→JSON parser (e.g. mistletoe or hybrid); write `structure.json` in session.
3. Implement Node script (converter.js) using docx: headings, paragraphs, code blocks, tables, images.
4. Python conversion node: call Node script, timeout (e.g. 120s), map success/failure to state.
5. Quality validator: load DOCX (python-docx), implement FC011 checks; set `quality_passed` and issue list; route pass/fail.

## Dependencies

- Epic 4: Validation, Checkpointing & Recovery (valid markdown).

## Priority

| Value     | Effort | Note                |
|-----------|--------|---------------------|
| Very High | High   | Delivers DOCX + FC011. |
