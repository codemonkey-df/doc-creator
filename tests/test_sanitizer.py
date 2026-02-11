"""Unit tests for InputSanitizer (Story 1.1). GIVEN-WHEN-THEN; security tests tagged."""

import pytest
from pathlib import Path

from backend.utils.exceptions import SecurityError, ValidationError
from backend.utils.sanitizer import InputSanitizer
from backend.utils.settings import SanitizerSettings


# --- Fixtures ---


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """GIVEN a temporary base directory."""
    return tmp_path.resolve()


@pytest.fixture
def valid_txt(base_dir: Path) -> Path:
    """GIVEN a valid .txt file under base_dir."""
    f = base_dir / "doc.txt"
    f.write_text("Hello UTF-8", encoding="utf-8")
    return f


@pytest.fixture
def sanitizer() -> InputSanitizer:
    """GIVEN default InputSanitizer (settings from defaults/env)."""
    return InputSanitizer()


# --- AC1.1.1: Path resolution and directory boundary (security) ---


@pytest.mark.security
def test_rejects_path_traversal(sanitizer: InputSanitizer, base_dir: Path) -> None:
    """GIVEN base_dir / WHEN validate with ../ escape / THEN SecurityError."""
    path_with_traversal = str(base_dir / "sub" / ".." / ".." / "etc" / "passwd")
    with pytest.raises(SecurityError):
        sanitizer.validate(path_with_traversal, base_dir)


@pytest.mark.security
def test_rejects_path_outside_base(sanitizer: InputSanitizer, tmp_path: Path) -> None:
    """GIVEN base_dir A / WHEN path under another dir B / THEN SecurityError."""
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other_file = other_dir / "file.txt"
    other_file.write_text("x", encoding="utf-8")
    with pytest.raises(SecurityError):
        sanitizer.validate(str(other_file), base_dir.resolve())


@pytest.mark.security
def test_rejects_symlink_outside_base(
    sanitizer: InputSanitizer, tmp_path: Path
) -> None:
    """GIVEN base_dir / WHEN path is symlink pointing outside / THEN SecurityError."""
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    link_inside = base_dir / "link.txt"
    link_inside.symlink_to(target)
    with pytest.raises(SecurityError):
        sanitizer.validate(str(link_inside), base_dir.resolve())


# --- AC1.1.2: Extension whitelist and blocklist ---


def test_accepts_whitelist_extensions(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN .txt, .log, .md files / WHEN validate / THEN returns resolved Path."""
    for ext in [".txt", ".log", ".md"]:
        f = base_dir / f"f{ext}"
        f.write_text("ok", encoding="utf-8")
        result = sanitizer.validate(str(f), base_dir)
        assert result == f.resolve()
        assert result.suffix == ext


def test_rejects_blocklist_extension_with_code(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN .exe file / WHEN validate / THEN ValidationError with EXTENSION_BLOCKED."""
    f = base_dir / "x.exe"
    f.write_bytes(b"MZ")
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "EXTENSION_BLOCKED"


def test_rejects_blocklist_sh(sanitizer: InputSanitizer, base_dir: Path) -> None:
    """GIVEN .sh file / WHEN validate / THEN ValidationError EXTENSION_BLOCKED."""
    f = base_dir / "script.sh"
    f.write_text("#!/bin/sh", encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "EXTENSION_BLOCKED"


def test_rejects_non_whitelist_extension(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN .py file (not in whitelist) / WHEN validate / THEN EXTENSION_NOT_ALLOWED."""
    f = base_dir / "x.py"
    f.write_text("print(1)", encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "EXTENSION_NOT_ALLOWED"


# --- AC1.1.3: File size limit ---


def test_rejects_file_over_size_limit(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN file larger than 100MB / WHEN validate / THEN ValidationError FILE_TOO_LARGE."""
    f = base_dir / "big.txt"
    # Create file of size > default limit without reading into memory
    with open(f, "wb") as fp:
        fp.seek(104_857_601)
        fp.write(b"x")
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "FILE_TOO_LARGE"


def test_accepts_file_at_exactly_limit(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN file exactly at size limit / WHEN validate / THEN passes (if UTF-8)."""
    f = base_dir / "exact.txt"
    with open(f, "wb") as fp:
        fp.write(b"x" * 104_857_600)
    result = sanitizer.validate(str(f), base_dir)
    assert result == f.resolve()


def test_respects_configurable_size_limit(base_dir: Path) -> None:
    """GIVEN SanitizerSettings with small max / WHEN file exceeds it / THEN FILE_TOO_LARGE."""
    settings = SanitizerSettings(max_file_size_bytes=10)
    sanitizer = InputSanitizer(settings=settings)
    f = base_dir / "small.txt"
    f.write_text("0123456789ab", encoding="utf-8")  # 12 bytes
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "FILE_TOO_LARGE"


# --- AC1.1.4: UTF-8 / binary ---


def test_rejects_invalid_utf8(sanitizer: InputSanitizer, base_dir: Path) -> None:
    """GIVEN file with invalid UTF-8 / WHEN validate / THEN ValidationError INVALID_UTF8."""
    f = base_dir / "bad.txt"
    f.write_bytes(b"ok \xff \xfe")
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "INVALID_UTF8"


def test_rejects_binary_null_byte(sanitizer: InputSanitizer, base_dir: Path) -> None:
    """GIVEN file with null byte / WHEN validate / THEN INVALID_UTF8 (binary sniff)."""
    f = base_dir / "bin.txt"
    f.write_bytes(b"hello\x00world")
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "INVALID_UTF8"


def test_accepts_valid_utf8(
    sanitizer: InputSanitizer, valid_txt: Path, base_dir: Path
) -> None:
    """GIVEN valid UTF-8 .txt / WHEN validate / THEN returns Path."""
    result = sanitizer.validate(str(valid_txt), base_dir)
    assert result == valid_txt.resolve()


# --- AC1.1.5: Exception types ---


def test_missing_file_raises_filenotfound(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN non-existent path / WHEN validate / THEN FileNotFoundError."""
    missing = base_dir / "nonexistent.txt"
    with pytest.raises(FileNotFoundError):
        sanitizer.validate(str(missing), base_dir)


def test_rejects_directory_path_with_path_not_file(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN path that is a directory under base_dir / WHEN validate / THEN ValidationError with code PATH_NOT_FILE."""
    subdir = base_dir / "subdir"
    subdir.mkdir()
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(subdir), base_dir)
    assert exc_info.value.code == "PATH_NOT_FILE"


# --- AC1.1.6: Public API ---


def test_validate_returns_resolved_path(
    sanitizer: InputSanitizer, valid_txt: Path, base_dir: Path
) -> None:
    """GIVEN valid path / WHEN validate / THEN returns resolved Path."""
    result = sanitizer.validate(str(valid_txt), base_dir)
    assert isinstance(result, Path)
    assert result.is_absolute()
    assert result.exists()
    assert result.suffix == ".txt"


# --- AC1.1.7: Validation order (exists before extension; size before read) ---


def test_missing_file_raises_before_extension_check(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN missing .exe path / WHEN validate / THEN FileNotFoundError (not EXTENSION_BLOCKED)."""
    missing_exe = base_dir / "missing.exe"
    with pytest.raises(FileNotFoundError):
        sanitizer.validate(str(missing_exe), base_dir)


def test_size_checked_with_stat_not_read(
    sanitizer: InputSanitizer, base_dir: Path
) -> None:
    """GIVEN oversized file / WHEN validate / THEN FILE_TOO_LARGE (size via stat, not read)."""
    f = base_dir / "huge.txt"
    with open(f, "wb") as fp:
        fp.seek(104_857_601)
        fp.write(b"x")
    with pytest.raises(ValidationError) as exc_info:
        sanitizer.validate(str(f), base_dir)
    assert exc_info.value.code == "FILE_TOO_LARGE"
