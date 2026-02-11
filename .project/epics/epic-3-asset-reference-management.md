# Epic 3: Asset & Reference Management

## Brief Description

Resolve image and path references: discover references in inputs, copy images into session assets, and handle missing files (placeholders or user resolution).

## Business Value

- Documents with images and external refs work reliably.
- Fewer conversion failures and clear handling of missing assets.

## Acceptance Criteria

- **FC008:** Detect relative/absolute image paths in markdown; resolve or copy into session; update refs to session-local paths.
- **FC014:** Validate image existence before use; copy to session `assets/`; insert placeholder text when missing.
- Scan runs after initialization; missing refs can trigger human-in-the-loop (Epic 2).

## High-Level Stories (4)

1. Asset scan node: parse input files for image refs (`![...](path)`), resolve paths, detect missing.
2. Copy available images to session `assets/` and rewrite refs to relative paths.
3. Add `copy_image` tool and integrate with agent for on-demand asset handling.
4. Placeholder insertion for missing images and optional prompt to user (integrate with Epic 2 interrupt).

## Dependencies

- Epic 1: Secure Input & Session Foundation.
- Integrates with Epic 2 (human-in-the-loop for missing refs).

## Priority

| Value | Effort | Note                   |
|-------|--------|------------------------|
| High  | Medium | Unblocks real-world docs. |
