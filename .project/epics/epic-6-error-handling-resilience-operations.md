# Epic 6: Error Handling, Resilience & Operations

## Brief Description

Classify conversion and validation errors, apply specialized fixes (syntax, encoding, asset, structural), enforce retry limits and graceful degradation, and add observability and production readiness.

## Business Value

- Self-healing where possible; predictable failure behavior and clear reporting.
- Operable and secure in production (logging, config, deployment, security).

## Acceptance Criteria

- **FC005:** Granular fixes (e.g. by line) where applicable; no full-doc rewrite when not needed.
- **FC013:** Classify errors (Syntax, Encoding, Asset, Structural, Unknown); route to correct handler.
- **FC017:** Max 3 conversion attempts; on final failure save best-effort markdown + error report and guidance.
- **FC015:** Structured JSON logging (state transitions, tool calls, errors) per session.
- Deployment checklist, env-based config, and security practices (sandboxing, no content in logs) addressed.

## High-Level Stories (5)

1. Error classifier: parse error message/location, return type + metadata; wire into error handler node.
2. Specialized handlers: Syntax (e.g. unclosed fences), Encoding (UTF-8), Asset (placeholder), Structural (heading hierarchy); each updates session files.
3. Error handler node: classify → invoke handler → rollback if applicable (Epic 4) → increment retry; conditional edge retry vs fail.
4. Save-results node: on success archive session; on failure write FAILED_conversion.md + ERROR_REPORT.txt and set status.
5. Structured logger (FC015): session-scoped JSONL logs; log state transitions, tool calls, errors; add config (env), deployment checklist, and security notes to docs/code.

## Dependencies

- Epic 4: Validation, Checkpointing & Recovery (rollback).
- Epic 5: DOCX Conversion & Output Quality (conversion failure handling).

## Priority

| Value | Effort | Note                |
|-------|--------|---------------------|
| High  | Medium | Production readiness. |
