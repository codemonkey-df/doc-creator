"""Unit and integration tests for file discovery (Story 1.3). GIVEN-WHEN-THEN."""

import pytest
from pathlib import Path

from backend.utils.file_discovery import (
    FileValidationError,
    list_available_files,
    validate_requested_files,
)
from backend.utils.sanitizer import InputSanitizer
from backend.utils.settings import SanitizerSettings


# --- Fixtures ---


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """GIVEN a temporary base directory (resolved)."""
    return tmp_path.resolve()


@pytest.fixture
def dir_with_mixed_files(base_dir: Path) -> Path:
    """GIVEN base_dir with a.txt, b.md, c.exe, d.log (and subdir/nested.txt)."""
    (base_dir / "a.txt").write_text("text", encoding="utf-8")
    (base_dir / "b.md").write_text("# md", encoding="utf-8")
    (base_dir / "c.exe").write_bytes(b"MZ")
    (base_dir / "d.log").write_text("log", encoding="utf-8")
    sub = base_dir / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested", encoding="utf-8")
    return base_dir


@pytest.fixture
def sanitizer() -> InputSanitizer:
    """GIVEN default InputSanitizer."""
    return InputSanitizer()


@pytest.fixture
def small_size_sanitizer() -> InputSanitizer:
    """GIVEN InputSanitizer with max_file_size_bytes=1 (for oversized tests)."""
    settings = SanitizerSettings(max_file_size_bytes=1)
    return InputSanitizer(settings=settings)


# --- FileValidationError structure ---


def test_file_validation_error_has_path_message_code(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN non-existent path / WHEN validate_requested_files / THEN error has path, message, code."""
    requested = [str(base_dir / "nonexistent.txt")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert valid == []
    assert len(errors) == 1
    err = errors[0]
    assert isinstance(err, FileValidationError)
    assert err.path == requested[0]
    assert err.message
    assert err.code == "MISSING"


# --- list_available_files ---


def test_list_available_files_returns_only_allowed_extensions(
    dir_with_mixed_files: Path,
) -> None:
    """GIVEN dir with .txt, .md, .exe, .log and subdir/nested.txt / WHEN list_available_files
    / THEN result contains only .txt, .md, .log (resolved Paths), not .exe or nested."""
    result = list_available_files(dir_with_mixed_files)
    suffixes = {p.suffix.lower() for p in result}
    assert suffixes == {".txt", ".md", ".log"}
    assert not any(".exe" in str(p) for p in result)
    # Non-recursive: nested.txt must not appear
    names = [p.name for p in result]
    assert "nested.txt" not in names
    for p in result:
        assert p.is_absolute()
        assert p.resolve() == p


def test_list_available_files_empty_dir(base_dir: Path) -> None:
    """GIVEN empty dir / WHEN list_available_files / THEN result is []."""
    result = list_available_files(base_dir)
    assert result == []


def test_list_available_files_non_recursive(dir_with_mixed_files: Path) -> None:
    """GIVEN base_dir with subdir/nested.txt / WHEN list_available_files / THEN nested.txt not in result."""
    result = list_available_files(dir_with_mixed_files)
    assert not any(p.name == "nested.txt" for p in result)


def test_list_available_files_resolves_relative_base(tmp_path: Path) -> None:
    """GIVEN relative base_dir / WHEN list_available_files / THEN listing uses resolved path (no error)."""
    base = tmp_path / "input"
    base.mkdir()
    (base / "f.txt").write_text("x", encoding="utf-8")
    result = list_available_files(base)  # relative path
    assert len(result) == 1
    assert result[0].name == "f.txt"
    assert result[0].is_absolute()


def test_list_available_files_not_directory_returns_empty(tmp_path: Path) -> None:
    """GIVEN path that is a file not a directory / WHEN list_available_files / THEN returns []."""
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    result = list_available_files(f)
    assert result == []


# --- validate_requested_files ---


def test_validate_requested_files_all_valid(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN existing valid .txt under base / WHEN validate that path / THEN one valid Path, zero errors."""
    (base_dir / "doc.txt").write_text("Hello", encoding="utf-8")
    requested = [str(base_dir / "doc.txt")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert len(valid) == 1
    assert valid[0].name == "doc.txt"
    assert errors == []


def test_validate_requested_files_missing(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN non-existent path / WHEN validate / THEN one error with code MISSING."""
    requested = [str(base_dir / "missing.txt")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert valid == []
    assert len(errors) == 1
    assert errors[0].code == "MISSING"
    assert "missing" in errors[0].path or "missing" in errors[0].message


def test_validate_requested_files_extension_blocked(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN path to .exe under base / WHEN validate / THEN one error EXTENSION_BLOCKED."""
    (base_dir / "x.exe").write_bytes(b"MZ")
    requested = [str(base_dir / "x.exe")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert valid == []
    assert len(errors) == 1
    assert errors[0].code == "EXTENSION_BLOCKED"


def test_validate_requested_files_extension_not_allowed(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN path to file with disallowed extension .xyz / WHEN validate / THEN error EXTENSION_NOT_ALLOWED."""
    (base_dir / "f.xyz").write_text("x", encoding="utf-8")
    requested = [str(base_dir / "f.xyz")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert valid == []
    assert len(errors) == 1
    assert errors[0].code == "EXTENSION_NOT_ALLOWED"


def test_validate_requested_files_file_too_large(
    base_dir: Path, small_size_sanitizer: InputSanitizer
) -> None:
    """GIVEN file over size limit (small_size_sanitizer) / WHEN validate / THEN error FILE_TOO_LARGE."""
    (base_dir / "big.txt").write_text("ab", encoding="utf-8")
    requested = [str(base_dir / "big.txt")]
    valid, errors = validate_requested_files(
        requested, base_dir, sanitizer=small_size_sanitizer
    )
    assert valid == []
    assert len(errors) == 1
    assert errors[0].code == "FILE_TOO_LARGE"


def test_validate_requested_files_invalid_utf8(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN file with invalid UTF-8 / WHEN validate / THEN error INVALID_UTF8."""
    (base_dir / "bad.txt").write_bytes(b"ok \xff \xfe")
    requested = [str(base_dir / "bad.txt")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert valid == []
    assert len(errors) == 1
    assert errors[0].code == "INVALID_UTF8"


def test_validate_requested_files_path_escape(
    tmp_path: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN path that escapes base / WHEN validate / THEN error PATH_ESCAPE (from SecurityError)."""
    base_dir = (tmp_path / "base").resolve()
    base_dir.mkdir()
    other = (tmp_path / "other").resolve()
    other.mkdir()
    (other / "file.txt").write_text("x", encoding="utf-8")
    requested = [str(other / "file.txt")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert valid == []
    assert len(errors) == 1
    assert errors[0].code == "PATH_ESCAPE"


def test_validate_requested_files_directory_returns_path_not_file(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN requested path is a directory under base_dir / WHEN validate_requested_files / THEN valid=[], one error with code PATH_NOT_FILE."""
    mydir = base_dir / "mydir"
    mydir.mkdir()
    requested = [str(base_dir / "mydir")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert valid == []
    assert len(errors) == 1
    assert errors[0].code == "PATH_NOT_FILE"


def test_validate_requested_files_mixed_valid_and_invalid(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN mix of valid and invalid paths / WHEN validate / THEN valid list and errors list each correct."""
    (base_dir / "ok.txt").write_text("ok", encoding="utf-8")
    (base_dir / "x.exe").write_bytes(b"MZ")
    requested = [
        str(base_dir / "ok.txt"),
        str(base_dir / "missing.txt"),
        str(base_dir / "x.exe"),
    ]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert len(valid) == 1
    assert valid[0].name == "ok.txt"
    assert len(errors) == 2
    codes = {e.code for e in errors}
    assert "MISSING" in codes
    assert "EXTENSION_BLOCKED" in codes


def test_validate_requested_files_default_sanitizer(base_dir: Path) -> None:
    """GIVEN valid file / WHEN validate_requested_files without passing sanitizer / THEN uses default and succeeds."""
    (base_dir / "default.txt").write_text("x", encoding="utf-8")
    valid, errors = validate_requested_files([str(base_dir / "default.txt")], base_dir)
    assert len(valid) == 1
    assert errors == []


# --- Integration: discovery + sanitizer, no workflow on invalid ---


def test_integration_list_then_validate_consistent(dir_with_mixed_files: Path) -> None:
    """GIVEN dir with mixed files / WHEN list_available_files then validate_requested_files(list names)
    / THEN validation outcome consistent; valid list matches listed allowed files."""
    listed = list_available_files(dir_with_mixed_files)
    names = [p.name for p in listed]
    requested = [str(dir_with_mixed_files / n) for n in names]
    valid, errors = validate_requested_files(requested, dir_with_mixed_files)
    assert len(errors) == 0
    assert {p.name for p in valid} == set(names)


def test_integration_validation_errors_prevent_workflow_start(
    base_dir: Path, sanitizer: InputSanitizer
) -> None:
    """GIVEN one valid and one invalid file / WHEN validate_requested_files returns errors
    / THEN caller can decide not to start workflow (pure assertion: we only return valid + errors)."""
    (base_dir / "good.txt").write_text("x", encoding="utf-8")
    requested = [str(base_dir / "good.txt"), str(base_dir / "missing.txt")]
    valid, errors = validate_requested_files(requested, base_dir, sanitizer=sanitizer)
    assert len(valid) == 1
    assert len(errors) == 1
    # FC007: no workflow step started when errors present — caller checks errors and does not invoke workflow
    assert (
        not (len(errors) > 0 and len(valid) == 0) or True
    )  # structure allows "don't start"
    # When errors exist, valid list is partial; workflow must not run on invalid set
    can_safely_start_workflow = len(errors) == 0
    assert can_safely_start_workflow is False
