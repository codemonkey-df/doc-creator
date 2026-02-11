# Epic 1: Secure Input & Session Foundation

## Brief Description

Implement secure, multi-format input handling and per-request session isolation so every conversion runs in a dedicated, safe environment.

## Business Value

- Prevents path traversal, executable uploads, and oversized files (security and stability).
- Enables concurrent runs without file clashes and clear audit per request.

## Acceptance Criteria

- **FC001:** Accept and validate `.txt`, `.log`, `.md` (UTF-8, max 100MB); reject binary/executable and paths outside allowed base.
- **FC007:** List and validate files in input directory before processing.
- **FC012:** One UUID session directory per request with `inputs/`, `assets/`, `checkpoints/`, `logs/`.
- **FC016:** Path sanitization, extension whitelist/blocklist, size limits enforced on every user path.

## High-Level Stories (4)

1. Implement `InputSanitizer` (path resolution, allowed/blocked extensions, size limit, directory boundary).
2. Implement `SessionManager` (create UUID dirs, cleanup/archive).
3. File discovery: list and validate requested files against filesystem before workflow start.
4. Copy validated inputs into session `inputs/` and wire session lifecycle into workflow entry.

## Dependencies

- None (foundation epic).

## Priority

| Value  | Effort | Note                |
|--------|--------|---------------------|
| High   | Medium | Enables all other work. |
