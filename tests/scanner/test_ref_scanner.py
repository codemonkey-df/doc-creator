"""Tests for the reference scanner module."""

import pytest
from pathlib import Path
import tempfile
import shutil

from src.scanner.ref_scanner import (
    Ref,
    scan_file,
    scan_files,
    PATTERN_IMAGE,
    PATTERN_PATH,
    PATTERN_URL,
    deduplicate_refs,
    ref_count_by_type,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp)


@pytest.fixture
def image_existing(temp_dir):
    """Fixture: markdown file with image reference to existing file."""
    md_file = temp_dir / "has_image.md"
    img_dir = temp_dir / "images"
    img_dir.mkdir()
    img_file = img_dir / "diagram.png"
    img_file.write_text("fake image content")

    md_file.write_text("""# Test

![diagram](images/diagram.png)

Some text.
""")
    return md_file


@pytest.fixture
def image_missing(temp_dir):
    """Fixture: markdown file with image reference to missing file."""
    md_file = temp_dir / "missing_image.md"

    md_file.write_text("""# Test

![missing diagram](images/does_not_exist.png)

Some text.
""")
    return md_file


@pytest.fixture
def path_existing(temp_dir):
    """Fixture: markdown file with path reference to existing file."""
    md_file = temp_dir / "has_link.md"
    target_dir = temp_dir / "docs"
    target_dir.mkdir()
    target_file = target_dir / "other.md"
    target_file.write_text("# Other document")

    md_file.write_text("""# Test

[other doc](docs/other.md)

Some text.
""")
    return md_file


@pytest.fixture
def path_missing(temp_dir):
    """Fixture: markdown file with path reference to missing file."""
    md_file = temp_dir / "missing_link.md"

    md_file.write_text("""# Test

[missing doc](docs/does_not_exist.md)

Some text.
""")
    return md_file


@pytest.fixture
def url_link(temp_dir):
    """Fixture: markdown file with URL link (should not be matched by path scanner)."""
    md_file = temp_dir / "url_link.md"

    md_file.write_text("""# Test

[Google](https://www.google.com)

[GitHub](http://github.com)

Some text.
""")
    return md_file


@pytest.fixture
def mixed_refs(temp_dir):
    """Fixture: markdown file with multiple mixed references."""
    md_file = temp_dir / "mixed.md"
    img_dir = temp_dir / "images"
    img_dir.mkdir()
    target_dir = temp_dir / "docs"
    target_dir.mkdir()

    # Create existing files
    (img_dir / "photo.png").write_text("fake")
    (target_dir / "guide.md").write_text("# Guide")

    md_file.write_text("""# Test Document

![photo](images/photo.png)

![missing photo](images/nothing.jpg)

[guide](docs/guide.md)

[missing doc](docs/nowhere.md)

[External](https://example.com)

Some text.
""")
    return md_file


class TestScanFile:
    """Tests for scan_file function."""

    def test_image_existing(self, image_existing):
        """Test image reference with existing file."""
        refs = scan_file(image_existing)

        assert len(refs) == 1
        ref = refs[0]
        assert ref.type == "image"
        assert ref.original == "![diagram](images/diagram.png)"
        assert ref.status == "found"
        assert ref.source_file == image_existing
        assert ref.line_number == 3

    def test_image_missing(self, image_missing):
        """Test image reference with missing file."""
        refs = scan_file(image_missing)

        assert len(refs) == 1
        ref = refs[0]
        assert ref.type == "image"
        assert ref.status == "missing"
        assert "does_not_exist.png" in str(ref.original)

    def test_path_existing(self, path_existing):
        """Test path reference with existing file."""
        refs = scan_file(path_existing)

        assert len(refs) == 1
        ref = refs[0]
        assert ref.type == "path"
        assert ref.original == "[other doc](docs/other.md)"
        assert ref.status == "found"
        assert ref.source_file == path_existing
        assert ref.line_number == 3

    def test_path_missing(self, path_missing):
        """Test path reference with missing file."""
        refs = scan_file(path_missing)

        assert len(refs) == 1
        ref = refs[0]
        assert ref.type == "path"
        assert ref.status == "missing"
        assert "does_not_exist.md" in str(ref.original)

    def test_url_not_matched(self, url_link):
        """Test that URL links are matched by URL scanner (not path scanner)."""
        refs = scan_file(url_link)

        # Should have 2 URL refs - URLs ARE matched now by URL scanner
        assert len(refs) == 2
        assert all(r.type == "url" for r in refs)
        assert all(r.status == "external" for r in refs)
        assert all(r.resolved_path is None for r in refs)

    def test_mixed_refs(self, mixed_refs):
        """Test mixed content with multiple refs."""
        refs = scan_file(mixed_refs)

        # Should have 5 refs: 2 images + 2 paths + 1 URL
        assert len(refs) == 5

        # Check image refs
        image_refs = [r for r in refs if r.type == "image"]
        assert len(image_refs) == 2
        assert any(r.status == "found" for r in image_refs)
        assert any(r.status == "missing" for r in image_refs)

        # Check path refs
        path_refs = [r for r in refs if r.type == "path"]
        assert len(path_refs) == 2
        assert any(r.status == "found" for r in path_refs)
        assert any(r.status == "missing" for r in path_refs)

        # Check URL refs
        url_refs = [r for r in refs if r.type == "url"]
        assert len(url_refs) == 1
        assert url_refs[0].status == "external"
        assert url_refs[0].resolved_path is None


class TestScanFiles:
    """Tests for scan_files function."""

    def test_multiple_files(self, image_existing, path_existing):
        """Test scanning multiple files."""
        refs = scan_files([image_existing, path_existing])

        assert len(refs) == 2
        assert any(r.source_file == image_existing for r in refs)
        assert any(r.source_file == path_existing for r in refs)

    def test_empty_list(self, temp_dir):
        """Test empty list returns empty results."""
        refs = scan_files([])
        assert refs == []

    def test_nonexistent_file(self, temp_dir):
        """Test nonexistent file is skipped."""
        nonexistent = temp_dir / "does_not_exist.md"
        refs = scan_files([nonexistent])
        assert refs == []


class TestPatterns:
    """Tests for regex patterns."""

    def test_pattern_image_basic(self):
        """Test basic image pattern matching."""
        match = PATTERN_IMAGE.search("![alt](path/to/image.png)")
        assert match is not None
        assert match.group(1) == "alt"
        assert match.group(2) == "path/to/image.png"

    def test_pattern_image_empty_alt(self):
        """Test image pattern with empty alt text."""
        match = PATTERN_IMAGE.search("![](path/to/image.png)")
        assert match is not None
        assert match.group(1) == ""
        assert match.group(2) == "path/to/image.png"

    def test_pattern_path_basic(self):
        """Test basic path pattern matching."""
        match = PATTERN_PATH.search("[text](path/to/file.md)")
        assert match is not None
        assert match.group(1) == "text"
        assert match.group(2) == "path/to/file.md"

    def test_pattern_path_excludes_images(self):
        """Test that path pattern excludes image links."""
        match = PATTERN_PATH.search("![image](path.png)")
        assert match is None

    def test_pattern_path_excludes_anchors(self):
        """Test that path pattern excludes anchor links."""
        match = PATTERN_PATH.search("[text](#section)")
        assert match is None


class TestRefDataclass:
    """Tests for Ref dataclass."""

    def test_ref_creation(self, temp_dir):
        """Test creating a Ref object."""
        md_file = temp_dir / "test.md"
        ref = Ref(
            type="image",
            original="![alt](img.png)",
            resolved_path=Path("/resolved/img.png"),
            status="found",
            source_file=md_file,
            line_number=5,
        )

        assert ref.type == "image"
        assert ref.original == "![alt](img.png)"
        assert ref.status == "found"
        assert ref.source_file == md_file
        assert ref.line_number == 5

    def test_ref_with_none_path(self, temp_dir):
        """Test Ref with None resolved_path."""
        md_file = temp_dir / "test.md"
        ref = Ref(
            type="path",
            original="[text](missing.md)",
            resolved_path=None,
            status="missing",
            source_file=md_file,
            line_number=1,
        )

        assert ref.resolved_path is None
        assert ref.status == "missing"


class TestPatternURL:
    """Tests for PATTERN_URL regex pattern."""

    def test_pattern_url_https(self):
        """Test HTTPS URL pattern matching."""
        match = PATTERN_URL.search("Check out https://github.com/user/repo")
        assert match is not None
        assert match.group(0) == "https://github.com/user/repo"

    def test_pattern_url_http(self):
        """Test HTTP URL pattern matching."""
        match = PATTERN_URL.search("Visit http://example.com for info")
        assert match is not None
        assert match.group(0) == "http://example.com"

    def test_pattern_url_no_match(self):
        """Test that plain text without URL returns None."""
        match = PATTERN_URL.search("This is just text")
        assert match is None

    def test_pattern_url_with_path(self):
        """Test URL with additional path components."""
        match = PATTERN_URL.search("See https://docs.python.org/3/library/re.html")
        assert match is not None
        assert match.group(0) == "https://docs.python.org/3/library/re.html"


class TestDeduplicateRefs:
    """Tests for deduplicate_refs function."""

    def test_deduplicate_removes_duplicates(self, temp_dir):
        """Test that duplicate refs are removed."""
        md_file = temp_dir / "test.md"
        md_file.write_text("[link](same.md)\n[link](same.md)")

        refs = scan_file(md_file)
        # Before dedup: 2 refs with same original
        assert len(refs) == 2

        deduped = deduplicate_refs(refs)
        # After dedup: 1 ref
        assert len(deduped) == 1

    def test_deduplicate_keeps_first_occurrence(self, temp_dir):
        """Test that first occurrence is kept."""
        md_file = temp_dir / "test.md"
        # Use the SAME original string for both to test deduplication
        md_file.write_text("[link](same.md)\n[link](same.md)")

        refs = scan_file(md_file)
        deduped = deduplicate_refs(refs)

        assert len(deduped) == 1
        assert deduped[0].original == "[link](same.md)"

    def test_deduplicate_empty_list(self):
        """Test empty list returns empty."""
        assert deduplicate_refs([]) == []

    def test_deduplicate_no_duplicates(self, temp_dir):
        """Test list with no duplicates is unchanged."""
        md_file1 = temp_dir / "file1.md"
        md_file1.write_text("[link1](file1.md)")
        md_file2 = temp_dir / "file2.md"
        md_file2.write_text("[link2](file2.md)")

        refs = scan_files([md_file1, md_file2])
        deduped = deduplicate_refs(refs)

        assert len(deduped) == 2


class TestRefCountByType:
    """Tests for ref_count_by_type function."""

    def test_ref_count_by_type_all_types(self, temp_dir):
        """Test counting refs of all types."""
        md_file = temp_dir / "mixed.md"
        img_dir = temp_dir / "images"
        img_dir.mkdir()
        (img_dir / "test.png").write_text("fake")

        md_file.write_text("""# Test
![image](images/test.png)
[path](nonexistent.md)
https://example.com
""")

        refs = scan_file(md_file)
        counts = ref_count_by_type(refs)

        assert counts["image"] == 1
        assert counts["path"] == 1
        assert counts["url"] == 1

    def test_ref_count_by_type_empty(self):
        """Test empty list returns zeros."""
        counts = ref_count_by_type([])
        assert counts == {"image": 0, "path": 0, "url": 0}

    def test_ref_count_by_type_only_urls(self, temp_dir):
        """Test counting only URLs."""
        md_file = temp_dir / "urls.md"
        md_file.write_text("https://a.com\nhttps://b.com\nhttps://a.com")

        refs = scan_file(md_file)
        counts = ref_count_by_type(refs)

        assert counts["url"] == 3
        assert counts["image"] == 0
        assert counts["path"] == 0


class TestScanFilesDeduplication:
    """Tests for scan_files deduplication."""

    def test_scan_files_deduplicates(self, temp_dir):
        """Test that scan_files returns deduplicated refs."""
        md_file1 = temp_dir / "file1.md"
        md_file2 = temp_dir / "file2.md"

        # Same URL in both files
        md_file1.write_text("https://github.com/user/project")
        md_file2.write_text("Check https://github.com/user/project here")

        refs = scan_files([md_file1, md_file2])

        # Should be deduplicated to 1 ref
        assert len(refs) == 1
        assert refs[0].original == "https://github.com/user/project"

    def test_scan_files_dedupe_multiple_urls(self, temp_dir):
        """Test deduplication with multiple different URLs."""
        md_file1 = temp_dir / "file1.md"
        md_file2 = temp_dir / "file2.md"

        md_file1.write_text("https://example.com\nhttps://test.com")
        md_file2.write_text("https://example.com")

        refs = scan_files([md_file1, md_file2])

        # 2 unique URLs
        assert len(refs) == 2

    def test_integration_url_dedup_across_files(self, temp_dir):
        """Integration test: same URL in 2+ files deduplicated to 1 Ref."""
        md_file1 = temp_dir / "doc1.md"
        md_file2 = temp_dir / "doc2.md"

        # Same URL appearing in multiple files
        url = "https://github.com/codemonkey/project"
        md_file1.write_text(f"See {url} for details")
        md_file2.write_text(f"Also check {url}")

        refs = scan_files([md_file1, md_file2])

        # Should be deduplicated to 1 Ref
        assert len(refs) == 1
        assert refs[0].type == "url"
        assert refs[0].original == url
        assert refs[0].status == "external"
