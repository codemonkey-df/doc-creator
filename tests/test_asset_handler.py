"""
Test suite for asset_handler module (Story 3.2: Copy Images and Rewrite Refs).

Tests cover:
- Copying found images to session assets/ directory
- Rewriting markdown references to use relative ./assets/basename paths
- Collision handling (last copy wins)
- UTF-8 and line ending preservation
- Idempotency of copy+rewrite operations
- Integration with scan_assets workflow
"""

import logging
from pathlib import Path
from typing import Generator

import pytest

from src.backend.state import ImageRefResult
from src.backend.utils.asset_handler import (
    apply_asset_scan_results,
    copy_found_images,
    rewrite_input_files,
    rewrite_refs_in_content,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def temp_session_path(tmp_path: Path) -> Path:
    """Create a temporary session directory structure."""
    session = tmp_path / "session"
    session.mkdir()
    (session / "inputs").mkdir()
    (session / "assets").mkdir()
    return session


@pytest.fixture
def temp_images_dir(tmp_path: Path) -> Path:
    """Create a directory with sample image files for testing."""
    images = tmp_path / "images"
    images.mkdir()
    (images / "diagram.png").touch()
    (images / "screenshot.jpg").touch()
    (images / "logo.gif").touch()
    return images


@pytest.fixture
def sample_markdown() -> str:
    """Sample markdown with image references."""
    return """# Document Title

Some introductory text.

![Diagram](./diagram.png)

More content here.

![Screenshot](./images/screenshot.jpg)

And another section.

![Logo](./logo.gif "Company Logo")

Final paragraph.
"""


@pytest.fixture
def markdown_with_special_chars() -> str:
    """Markdown with UTF-8 special characters."""
    return """# Документ с кириллицей

Текст с символами: €, ™, ©, 中文

![图像](./diagram.png)

More text with émojis 🎉 and ñ characters.

![Screenshot](./screenshot.jpg)
"""


@pytest.fixture
def caplog_handler(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Configure logging capture."""
    caplog.set_level(logging.DEBUG)
    return caplog


# ============================================================================
# UNIT TESTS: copy_found_images()
# ============================================================================


class TestCopyFoundImages:
    """Tests for copy_found_images function."""

    def test_copy_single_image_success(
        self, temp_session_path: Path, temp_images_dir: Path, caplog_handler: pytest.LogCaptureFixture
    ) -> None:
        """GIVEN single found image ref / WHEN copied / THEN file in assets and logged."""
        found_refs = [
            ImageRefResult(
                original_path="./diagram.png",
                resolved_path=str(temp_images_dir / "diagram.png"),
                source_file="doc.md",
            )
        ]

        result = copy_found_images(temp_session_path, found_refs)

        assert result == {"./diagram.png": "diagram.png"}
        assert (temp_session_path / "assets" / "diagram.png").exists()
        assert "copied" in caplog_handler.text.lower() or "copy" in caplog_handler.text.lower()

    def test_copy_multiple_images(
        self, temp_session_path: Path, temp_images_dir: Path
    ) -> None:
        """GIVEN multiple image refs / WHEN copied / THEN all in assets."""
        found_refs = [
            ImageRefResult(
                original_path="./diagram.png",
                resolved_path=str(temp_images_dir / "diagram.png"),
                source_file="doc.md",
            ),
            ImageRefResult(
                original_path="./screenshot.jpg",
                resolved_path=str(temp_images_dir / "screenshot.jpg"),
                source_file="doc.md",
            ),
        ]

        result = copy_found_images(temp_session_path, found_refs)

        assert len(result) == 2
        assert (temp_session_path / "assets" / "diagram.png").exists()
        assert (temp_session_path / "assets" / "screenshot.jpg").exists()

    def test_copy_duplicate_basename_last_wins(
        self, temp_session_path: Path, tmp_path: Path, caplog_handler: pytest.LogCaptureFixture
    ) -> None:
        """GIVEN multiple refs to different sources with same basename / WHEN copied / THEN last wins."""
        # Create two different image sources with same basename
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        img1 = dir1 / "image.png"
        img2 = dir2 / "image.png"
        img1.write_text("version1")
        img2.write_text("version2")

        found_refs = [
            ImageRefResult(
                original_path="../dir1/image.png",
                resolved_path=str(img1),
                source_file="doc1.md",
            ),
            ImageRefResult(
                original_path="../dir2/image.png",
                resolved_path=str(img2),
                source_file="doc2.md",
            ),
        ]

        result = copy_found_images(temp_session_path, found_refs)

        # Both original paths map to same basename
        assert result["../dir1/image.png"] == "image.png"
        assert result["../dir2/image.png"] == "image.png"

        # Last copy (version2) should be in assets
        assert (temp_session_path / "assets" / "image.png").read_text() == "version2"
        assert "overwrite" in caplog_handler.text.lower() or "collision" in caplog_handler.text.lower()

    def test_copy_nonexistent_source_skipped(
        self, temp_session_path: Path, caplog_handler: pytest.LogCaptureFixture
    ) -> None:
        """GIVEN found ref with nonexistent resolved path / WHEN copied / THEN skipped with warning."""
        found_refs = [
            ImageRefResult(
                original_path="./missing.png",
                resolved_path="/nonexistent/path/missing.png",
                source_file="doc.md",
            )
        ]

        result = copy_found_images(temp_session_path, found_refs)

        # Nonexistent file should not be copied
        assert not (temp_session_path / "assets" / "missing.png").exists()
        # Result may be empty or contain None mapping (depends on implementation)
        assert len(result) <= 1

    def test_copy_empty_found_refs(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN empty found refs list / WHEN copied / THEN no copies, empty result."""
        found_refs: list[ImageRefResult] = []

        result = copy_found_images(temp_session_path, found_refs)

        assert result == {}
        # No files in assets
        assets_files = list((temp_session_path / "assets").iterdir())
        assert len(assets_files) == 0

    def test_copy_preserves_file_content(
        self, temp_session_path: Path, tmp_path: Path
    ) -> None:
        """GIVEN image file with specific content / WHEN copied / THEN content preserved."""
        source = tmp_path / "source.png"
        source.write_bytes(b"PNG_BINARY_DATA_123")

        found_refs = [
            ImageRefResult(
                original_path="./source.png",
                resolved_path=str(source),
                source_file="doc.md",
            )
        ]

        copy_found_images(temp_session_path, found_refs)

        copied = temp_session_path / "assets" / "source.png"
        assert copied.read_bytes() == b"PNG_BINARY_DATA_123"


# ============================================================================
# UNIT TESTS: rewrite_refs_in_content()
# ============================================================================


class TestRewriteRefsInContent:
    """Tests for rewrite_refs_in_content function."""

    def test_rewrite_simple_ref(self) -> None:
        """GIVEN content with simple image ref / WHEN rewritten / THEN path updated, alt preserved."""
        content = "![Simple alt](./diagram.png)"

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        assert "![Simple alt](./assets/diagram.png)" in result

    def test_rewrite_ref_with_title(self) -> None:
        """GIVEN image ref with title / WHEN rewritten / THEN path updated, title lost (acceptable)."""
        content = '![alt](./diagram.png "Title Here")'

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        # Title may or may not be preserved (depends on implementation)
        # Main requirement is path is rewritten
        assert "./assets/diagram.png" in result
        assert "![" in result  # Alt text preserved

    def test_rewrite_multiple_same_ref_in_content(self) -> None:
        """GIVEN content with multiple refs to same path / WHEN rewritten / THEN all replaced."""
        content = """
![Diagram](./diagram.png)
Some text.
![Another diagram](./diagram.png)
More text.
        """

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        # Both occurrences should be rewritten
        count = result.count("./assets/diagram.png")
        assert count == 2

    def test_rewrite_only_image_syntax(self) -> None:
        """GIVEN content with path outside image syntax / WHEN rewritten / THEN only image syntax updated."""
        content = """Some text mentions ./diagram.png in a sentence.
![Image](./diagram.png)
Code block: ./diagram.png"""

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        # Only the image ref should be rewritten
        lines = [l.strip() for l in result.split("\n") if l.strip()]

        # First line with text mention should NOT be rewritten
        text_lines = [l for l in lines if "Some text mentions" in l]
        assert len(text_lines) > 0
        assert "./diagram.png" in text_lines[0]

        # Image syntax line SHOULD be rewritten
        image_lines = [l for l in lines if "![" in l]
        assert len(image_lines) > 0
        assert "./assets/diagram.png" in image_lines[0]

    def test_rewrite_preserves_alt_text_with_spaces(self) -> None:
        """GIVEN alt text with multiple spaces / WHEN rewritten / THEN alt preserved exactly."""
        content = "![Alt Text With Spaces](./diagram.png)"

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        assert "![Alt Text With Spaces]" in result

    def test_rewrite_empty_alt(self) -> None:
        """GIVEN image with empty alt / WHEN rewritten / THEN works correctly."""
        content = "![](./diagram.png)"

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        assert "![](./assets/diagram.png)" in result

    def test_rewrite_alt_with_special_chars(self) -> None:
        """GIVEN alt text with special chars / WHEN rewritten / THEN preserved."""
        content = "![Диаграмма 图表 €uro](./diagram.png)"

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        assert "![Диаграмма 图表 €uro]" in result
        assert "./assets/diagram.png" in result

    def test_rewrite_no_match_returns_unchanged(self) -> None:
        """GIVEN content without matching ref / WHEN rewritten / THEN unchanged."""
        content = "![Something](./other.png)"

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        assert result == content

    def test_rewrite_case_sensitive(self) -> None:
        """GIVEN path with different case / WHEN rewritten / THEN no match (case-sensitive)."""
        content = "![Image](./Diagram.png)"

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        # Should not match due to case difference
        assert "./Diagram.png" in result  # unchanged

    def test_rewrite_with_utf8_content(self) -> None:
        """GIVEN content with UTF-8 chars / WHEN rewritten / THEN preserved."""
        content = "Тест with émojis 🎉\n![图像](./diagram.png)\nMore text: ñ"

        result = rewrite_refs_in_content(content, "./diagram.png", "diagram.png")

        assert "Тест with émojis 🎉" in result
        assert "图像" in result
        assert "./assets/diagram.png" in result
        assert "ñ" in result


# ============================================================================
# UNIT TESTS: rewrite_input_files()
# ============================================================================


class TestRewriteInputFiles:
    """Tests for rewrite_input_files function."""

    def test_rewrite_single_file_with_refs(
        self, temp_session_path: Path, sample_markdown: str
    ) -> None:
        """GIVEN input file with image refs / WHEN rewritten / THEN file updated, count returned."""
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(sample_markdown)

        found_refs = [
            ImageRefResult(
                original_path="./diagram.png",
                resolved_path="/some/path/diagram.png",
                source_file="doc.md",
            ),
            ImageRefResult(
                original_path="./logo.gif",
                resolved_path="/some/path/logo.gif",
                source_file="doc.md",
            ),
        ]

        copy_results = {"./diagram.png": "diagram.png", "./logo.gif": "logo.gif"}

        result = rewrite_input_files(temp_session_path, found_refs, copy_results)

        # Check file was rewritten
        updated_content = input_file.read_text()
        assert "./assets/diagram.png" in updated_content
        assert "./assets/logo.gif" in updated_content

        # Check result includes rewrite count
        assert "doc.md" in result
        assert result["doc.md"] >= 2  # At least 2 refs rewritten

    def test_rewrite_multiple_files(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN multiple input files with refs / WHEN rewritten / THEN all updated correctly."""
        # Create two input files
        file1 = temp_session_path / "inputs" / "doc1.md"
        file2 = temp_session_path / "inputs" / "doc2.md"

        content1 = "![Image1](./image.png)"
        content2 = "![Image2](./image.png)"

        file1.write_text(content1)
        file2.write_text(content2)

        found_refs = [
            ImageRefResult(
                original_path="./image.png",
                resolved_path="/path/image.png",
                source_file="doc1.md",
            ),
            ImageRefResult(
                original_path="./image.png",
                resolved_path="/path/image.png",
                source_file="doc2.md",
            ),
        ]

        copy_results = {"./image.png": "image.png"}

        result = rewrite_input_files(temp_session_path, found_refs, copy_results)

        # Both files should be updated
        assert file1.read_text().count("./assets/image.png") == 1
        assert file2.read_text().count("./assets/image.png") == 1

    def test_rewrite_preserves_utf8_encoding(
        self, temp_session_path: Path, markdown_with_special_chars: str
    ) -> None:
        """GIVEN input file with UTF-8 content / WHEN rewritten / THEN encoding preserved."""
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(markdown_with_special_chars, encoding="utf-8")

        found_refs = [
            ImageRefResult(
                original_path="./diagram.png",
                resolved_path="/path/diagram.png",
                source_file="doc.md",
            ),
        ]

        copy_results = {"./diagram.png": "diagram.png"}

        rewrite_input_files(temp_session_path, found_refs, copy_results)

        # Read back and check UTF-8 preserved
        updated = input_file.read_text(encoding="utf-8")
        assert "Документ с кириллицей" in updated
        assert "中文" in updated
        assert "émojis 🎉" in updated

    def test_rewrite_preserves_line_endings_lf(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN file with LF line endings / WHEN rewritten / THEN LF preserved."""
        input_file = temp_session_path / "inputs" / "doc.md"
        content = "Line 1\nLine 2 with ![image](./image.png)\nLine 3\n"
        input_file.write_bytes(content.encode("utf-8"))

        found_refs = [
            ImageRefResult(
                original_path="./image.png",
                resolved_path="/path/image.png",
                source_file="doc.md",
            ),
        ]

        copy_results = {"./image.png": "image.png"}

        rewrite_input_files(temp_session_path, found_refs, copy_results)

        # Check line endings are still LF
        updated_bytes = input_file.read_bytes()
        assert b"\r\n" not in updated_bytes  # No CRLF
        assert b"\n" in updated_bytes  # Has LF

    def test_rewrite_preserves_line_endings_crlf(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN file with CRLF line endings / WHEN rewritten / THEN CRLF preserved."""
        input_file = temp_session_path / "inputs" / "doc.md"
        # Create content with CRLF
        content = "Line 1\r\nLine 2 with ![image](./image.png)\r\nLine 3\r\n"
        input_file.write_bytes(content.encode("utf-8"))

        found_refs = [
            ImageRefResult(
                original_path="./image.png",
                resolved_path="/path/image.png",
                source_file="doc.md",
            ),
        ]

        copy_results = {"./image.png": "image.png"}

        rewrite_input_files(temp_session_path, found_refs, copy_results)

        # Check line endings are CRLF preserved
        updated_bytes = input_file.read_bytes()
        assert b"\r\n" in updated_bytes  # Still has CRLF
        # After rewrite, content should still be valid
        assert b"./assets/image.png" in updated_bytes

    def test_rewrite_nonexistent_file_skipped(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN ref to file that doesn't exist / WHEN rewrite / THEN skipped gracefully."""
        found_refs = [
            ImageRefResult(
                original_path="./image.png",
                resolved_path="/path/image.png",
                source_file="nonexistent.md",
            ),
        ]

        copy_results = {"./image.png": "image.png"}

        # Should not raise error
        result = rewrite_input_files(temp_session_path, found_refs, copy_results)

        # File should not be in result (or have 0 rewrites)
        assert "nonexistent.md" not in result or result.get("nonexistent.md", 0) == 0

    def test_rewrite_no_matching_refs_in_file(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN file without any refs / WHEN rewrite / THEN no changes, 0 count."""
        input_file = temp_session_path / "inputs" / "doc.md"
        original_content = "Just text, no images.\n"
        input_file.write_text(original_content)

        found_refs = [
            ImageRefResult(
                original_path="./image.png",
                resolved_path="/path/image.png",
                source_file="doc.md",
            ),
        ]

        copy_results = {"./image.png": "image.png"}

        result = rewrite_input_files(temp_session_path, found_refs, copy_results)

        # File should be unchanged
        assert input_file.read_text() == original_content
        # Count should be 0
        assert result.get("doc.md", 0) == 0

    def test_rewrite_idempotent_on_same_refs(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN same refs applied twice / WHEN rewritten / THEN result identical (idempotent)."""
        input_file = temp_session_path / "inputs" / "doc.md"
        original = "![Image](./image.png)"
        input_file.write_text(original)

        found_refs = [
            ImageRefResult(
                original_path="./image.png",
                resolved_path="/path/image.png",
                source_file="doc.md",
            ),
        ]

        copy_results = {"./image.png": "image.png"}

        # Apply once
        rewrite_input_files(temp_session_path, found_refs, copy_results)
        result1 = input_file.read_text()

        # Apply again
        rewrite_input_files(temp_session_path, found_refs, copy_results)
        result2 = input_file.read_text()

        # Results should be identical (idempotent)
        assert result1 == result2
        assert "./assets/image.png" in result2


# ============================================================================
# INTEGRATION TESTS: apply_asset_scan_results()
# ============================================================================


class TestApplyAssetScanResults:
    """Integration tests for apply_asset_scan_results function."""

    def test_apply_full_workflow_single_file(
        self, temp_session_path: Path, temp_images_dir: Path, sample_markdown: str
    ) -> None:
        """GIVEN sample markdown with image refs / WHEN applied / THEN copies and rewrites both happen."""
        # Setup input file
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(sample_markdown)

        # Prepare found refs (as would come from scan_assets)
        found_refs = [
            ImageRefResult(
                original_path="./diagram.png",
                resolved_path=str(temp_images_dir / "diagram.png"),
                source_file="doc.md",
            ),
        ]

        # Apply full workflow
        result = apply_asset_scan_results(temp_session_path, found_refs)

        # Verify copy happened
        assert (temp_session_path / "assets" / "diagram.png").exists()

        # Verify rewrite happened
        updated_content = input_file.read_text()
        assert "./assets/diagram.png" in updated_content
        assert "![Diagram]" in updated_content  # Alt preserved

        # Verify result contains stats
        assert "copied" in result
        assert "rewritten" in result

    def test_apply_with_duplicate_basenames(
        self, temp_session_path: Path, tmp_path: Path
    ) -> None:
        """GIVEN refs with duplicate basenames / WHEN applied / THEN last copy wins, all refs rewritten."""
        # Create two images with same basename
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        img1 = dir1 / "image.png"
        img2 = dir2 / "image.png"
        img1.write_text("version1")
        img2.write_text("version2")

        # Create input file with both refs
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(
            "![Ref1](../dir1/image.png)\nSome text\n![Ref2](../dir2/image.png)\n"
        )

        found_refs = [
            ImageRefResult(
                original_path="../dir1/image.png",
                resolved_path=str(img1),
                source_file="doc.md",
            ),
            ImageRefResult(
                original_path="../dir2/image.png",
                resolved_path=str(img2),
                source_file="doc.md",
            ),
        ]

        result = apply_asset_scan_results(temp_session_path, found_refs)

        # Last version should be in assets
        assert (temp_session_path / "assets" / "image.png").read_text() == "version2"

        # Both refs in markdown should be rewritten to same path
        updated = input_file.read_text()
        assert updated.count("./assets/image.png") == 2

    def test_apply_empty_found_refs_no_op(
        self, temp_session_path: Path
    ) -> None:
        """GIVEN empty found refs / WHEN applied / THEN no-op, assets empty."""
        found_refs: list[ImageRefResult] = []

        result = apply_asset_scan_results(temp_session_path, found_refs)

        # No copies should have happened
        assets_files = list((temp_session_path / "assets").iterdir())
        assert len(assets_files) == 0

        # Result should indicate no work done
        assert result.get("copied", 0) == 0

    def test_apply_preserves_file_encoding_and_line_endings(
        self, temp_session_path: Path, tmp_path: Path
    ) -> None:
        """GIVEN file with UTF-8 and CRLF / WHEN applied / THEN both preserved."""
        # Create input with UTF-8 and CRLF
        input_file = temp_session_path / "inputs" / "doc.md"
        content_with_crlf = "# Тест\r\n![图像](./image.png)\r\n"
        input_file.write_bytes(content_with_crlf.encode("utf-8"))

        # Create image
        img = tmp_path / "image.png"
        img.touch()

        found_refs = [
            ImageRefResult(
                original_path="./image.png",
                resolved_path=str(img),
                source_file="doc.md",
            ),
        ]

        apply_asset_scan_results(temp_session_path, found_refs)

        # Verify encoding and line endings preserved
        updated_bytes = input_file.read_bytes()
        assert "Тест".encode("utf-8") in updated_bytes
        assert "图像".encode("utf-8") in updated_bytes
        assert b"\r\n" in updated_bytes  # CRLF preserved

    def test_apply_idempotent_on_rerun(
        self, temp_session_path: Path, temp_images_dir: Path, sample_markdown: str
    ) -> None:
        """GIVEN applied once / WHEN applied again / THEN result identical (idempotent)."""
        input_file = temp_session_path / "inputs" / "doc.md"
        input_file.write_text(sample_markdown)

        found_refs = [
            ImageRefResult(
                original_path="./diagram.png",
                resolved_path=str(temp_images_dir / "diagram.png"),
                source_file="doc.md",
            ),
        ]

        # First application
        result1 = apply_asset_scan_results(temp_session_path, found_refs)
        content1 = input_file.read_text()
        assets1 = set((temp_session_path / "assets").iterdir())

        # Second application (same refs)
        result2 = apply_asset_scan_results(temp_session_path, found_refs)
        content2 = input_file.read_text()
        assets2 = set((temp_session_path / "assets").iterdir())

        # Both should be identical
        assert content1 == content2
        assert assets1 == assets2
