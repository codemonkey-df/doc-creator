"""Tests for pipeline module."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.pipeline.pipeline import (
    PipelineError,
    validate_config,
    scan_references,
    resolve_references,
    write_output,
    slugify,
    run_pipeline,
)
from src.tui.state import AppState, ChapterEntry


class TestPipelineError:
    """Tests for PipelineError exception."""

    def test_error_stores_stage_and_message(self):
        """PipelineError stores stage and message correctly."""
        error = PipelineError("validate", "Document title required")
        assert error.stage == "validate"
        assert error.message == "Document title required"

    def test_error_message_format(self):
        """PipelineError formats message correctly."""
        error = PipelineError("validate", "Document title required")
        assert str(error) == "[validate] Document title required"


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_empty_title_raises_error(self):
        """Empty title raises PipelineError."""
        state = AppState(
            title="", intro_file="intro.md", chapters=[ChapterEntry("ch1.md")]
        )
        with pytest.raises(PipelineError) as exc:
            validate_config(state)
        assert exc.value.stage == "validate"
        assert "Document title required" in exc.value.message

    def test_untitled_raises_error(self):
        """Title 'Untitled' raises PipelineError."""
        state = AppState(
            title="Untitled", intro_file="intro.md", chapters=[ChapterEntry("ch1.md")]
        )
        with pytest.raises(PipelineError) as exc:
            validate_config(state)
        assert "Document title required" in exc.value.message

    def test_no_intro_raises_error(self):
        """Missing intro file raises PipelineError (unless imported file is set)."""
        state = AppState(
            title="My Doc", intro_file=None, chapters=[ChapterEntry("ch1.md")]
        )
        with pytest.raises(PipelineError) as exc:
            validate_config(state)
        assert exc.value.stage == "validate"
        assert "Introduction file or imported file required" in exc.value.message

    def test_no_chapters_raises_error(self):
        """Missing chapters raises PipelineError."""
        state = AppState(title="My Doc", intro_file="intro.md", chapters=[])
        with pytest.raises(PipelineError) as exc:
            validate_config(state)
        assert exc.value.stage == "validate"
        assert "At least one chapter required" in exc.value.message

    def test_valid_config_passes(self):
        """Valid config passes validation."""
        state = AppState(
            title="My Doc", intro_file="intro.md", chapters=[ChapterEntry("ch1.md")]
        )
        # Should not raise
        validate_config(state)


class TestSlugify:
    """Tests for slugify function."""

    def test_lowercase(self):
        """Converts to lowercase."""
        assert slugify("Hello World") == "hello-world"

    def test_spaces_to_dashes(self):
        """Replaces spaces with dashes."""
        assert slugify("Hello   World") == "hello-world"

    def test_removes_special_chars(self):
        """Removes non-alphanumeric characters."""
        assert slugify("Hello, World! (2024)") == "hello-world-2024"

    def test_removes_leading_trailing_dashes(self):
        """Removes leading and trailing dashes."""
        assert slugify("  Hello  ") == "hello"

    def test_multiple_dashes_collapsed(self):
        """Collapses multiple dashes to single dash."""
        assert slugify("Hello   ---   World") == "hello-world"


class TestWriteOutput:
    """Tests for write_output function."""

    def setup_method(self):
        """Create temp directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)

    def teardown_method(self):
        """Restore original directory."""
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir)

    def test_creates_output_directory(self):
        """Creates output directory if it doesn't exist."""
        state = AppState(title="Test Doc")
        write_output("# Test", state)
        assert Path("output").is_dir()

    def test_writes_markdown_file(self):
        """Writes markdown content to file."""
        state = AppState(title="Test Doc")
        result = write_output("# Test Content", state)
        assert result == Path("output/test-doc.md")
        assert result.read_text() == "# Test Content"

    def test_special_chars_in_title(self):
        """Handles special characters in title."""
        state = AppState(title="My (Test) Document 2024!")
        result = write_output("# Content", state)
        assert result == Path("output/my-test-document-2024.md")


class TestScanReferences:
    """Tests for scan_references function."""

    def test_scans_intro_and_chapters(self):
        """Scans intro and chapter files."""
        # Create temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            intro_path = Path(tmpdir) / "intro.md"
            intro_path.write_text("![image](img.png)")

            chapter_path = Path(tmpdir) / "chapter.md"
            chapter_path.write_text("[link](other.md)")

            state = AppState(
                intro_file=str(intro_path),
                chapters=[ChapterEntry(str(chapter_path))],
            )

            refs = scan_references(state)
            # Should find image ref from intro and path ref from chapter
            assert len(refs) >= 1


class TestResolveReferences:
    """Tests for resolve_references function."""

    def test_skips_all_refs(self):
        """Placeholder returns all refs as skipped."""
        mock_ref = MagicMock()
        state = AppState()
        resolved = resolve_references([mock_ref], state)
        assert resolved.skipped == [mock_ref]
        assert resolved.provided == []
        assert resolved.to_summarize == []


class TestRunPipeline:
    """Tests for run_pipeline function."""

    def setup_method(self):
        """Create temp directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)

    def teardown_method(self):
        """Restore original directory."""
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir)

    def test_validation_error_logged(self):
        """Validation errors are logged to state.log_lines."""
        state = AppState(title="", intro_file=None, chapters=[])
        run_pipeline(state)
        assert any("Starting pipeline" in line for line in state.log_lines)
        assert any(
            "Error" in line and "title required" in line for line in state.log_lines
        )

    def test_successful_pipeline(self):
        """Successful pipeline logs all stages."""
        # Create temp files
        intro_path = Path(self.temp_dir) / "intro.md"
        intro_path.write_text("# Introduction\n\nIntro content")

        chapter_path = Path(self.temp_dir) / "chapter.md"
        chapter_path.write_text("# Chapter 1\n\nChapter content")

        state = AppState(
            title="Test Doc",
            intro_file=str(intro_path),
            chapters=[ChapterEntry(str(chapter_path))],
        )

        # Mock the LLM call to avoid actual API calls
        with patch("src.pipeline.pipeline.generate_content") as mock_gen:
            mock_gen.return_value = "# Test Document\n\nContent"

            run_pipeline(state)

            # Check log lines
            assert any("Starting pipeline" in line for line in state.log_lines)
            assert any("Scanning references" in line for line in state.log_lines)
            assert any("Generating content" in line for line in state.log_lines)
            assert any("Writing output" in line for line in state.log_lines)
            assert any("Done." in line for line in state.log_lines)

            # Check output file was created
            output_path = Path("output/test-doc.md")
            assert output_path.exists()
