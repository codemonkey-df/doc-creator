## EPIC 2 — Reference Scanner
**Milestone:** Before generation, the system detects all image/path/URL references in selected files and classifies them.
**Goal:** `ref_scanner.scan_files(paths)` returns a typed list of every reference found, with status `found / missing / external`. No user interaction yet.
**Done when:** Scanner works correctly on all reference types with full unit test coverage.

---

### Story 2.1 — Ref Dataclass & Image/Path Scanner

**Description**
Create the `Ref` dataclass and implement regex detection for image refs (`![alt](path)`) and path refs (`[text](path)`), with path resolution relative to the source file.

**Tasks**
- [ ] `src/scanner/ref_scanner.py`: define `Ref` dataclass with `type`, `original`, `resolved_path`, `status`, `source_file`, `line_number`
- [ ] `PATTERN_IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')`
- [ ] `PATTERN_PATH = re.compile(r'(?<!!)\[([^\]]*)\]\(([^)#\s]+)\)')` (exclude images, anchors)
- [ ] `scan_file(path: Path) -> list[Ref]`: reads file, applies both patterns line by line
- [ ] For each match: resolve path relative to source file's directory; set `status` to `found` or `missing`
- [ ] Skip URL-like paths in path scanner (those starting with `http`)
- [ ] `scan_files(paths: list[Path]) -> list[Ref]`: calls `scan_file` for each, returns combined list

**Acceptance Criteria**
- `![diagram](./images/d.png)` → `Ref(type="image", status="missing")` when file absent
- `![diagram](./images/d.png)` → `Ref(type="image", status="found")` when file exists
- `[see spec](./spec.md)` → `Ref(type="path", status="missing")` when file absent
- `[click here](https://example.com)` → NOT matched by path scanner (filtered out)

**Definition of Done**
- [ ] Unit tests: 6+ fixture `.md` files covering each case
- [ ] All tests pass with `uv run pytest`
- [ ] `scan_files([])` returns `[]` without error

---

### Story 2.2 — URL Scanner & Deduplication

**Description**
Add URL detection to the scanner and deduplicate refs so the same URL/path isn't listed twice across files.

**Tasks**
- [ ] `PATTERN_URL = re.compile(r'https?://[^\s\)\"<>]+')`
- [ ] Add URL scanning to `scan_file`; create `Ref(type="url", status="external")`
- [ ] `deduplicate_refs(refs: list[Ref]) -> list[Ref]`: keep first occurrence of each unique `original` value
- [ ] `scan_files` calls `deduplicate_refs` before returning
- [ ] Add `ref_count_by_type(refs)` helper: returns `{"image": N, "path": N, "url": N}`

**Acceptance Criteria**
- `https://github.com/x` appearing in 2 files → deduplicated to 1 `Ref`
- `ref_count_by_type` returns correct counts
- URL refs always have `status="external"` and `resolved_path=None`

**Definition of Done**
- [ ] Unit tests for URL pattern, deduplication, count helper
- [ ] All existing Story 2.1 tests still pass
- [ ] `scan_files` on 3 fixture files returns expected deduped list

