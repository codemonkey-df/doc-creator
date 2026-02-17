"""Tests for Error Classifier - Story 6.1"""

from backend.error_handlers import ErrorType, classify


class TestErrorType:
    """Test ErrorType enum values."""

    def test_error_type_has_five_values(self):
        """GIVEN the ErrorType enum
        WHEN accessing its members
        THEN there are exactly 5 error types
        """
        error_types = list(ErrorType)
        assert len(error_types) == 5

    def test_error_type_values(self):
        """GIVEN the ErrorType enum
        WHEN checking the values
        THEN they match the expected types
        """
        assert ErrorType.SYNTAX.value == "syntax"
        assert ErrorType.ENCODING.value == "encoding"
        assert ErrorType.ASSET.value == "asset"
        assert ErrorType.STRUCTURAL.value == "structural"
        assert ErrorType.UNKNOWN.value == "unknown"


class TestClassifyReturns:
    """Test classify function returns tuple of (ErrorType, ErrorMetadata)."""

    def test_classify_returns_tuple(self):
        """GIVEN a simple error message
        WHEN calling classify
        THEN it returns a tuple
        """
        result = classify("unknown error occurred")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_classify_returns_error_type_first(self):
        """GIVEN a simple error message
        WHEN calling classify
        THEN the first element is an ErrorType
        """
        result = classify("unknown error occurred")
        assert isinstance(result[0], ErrorType)

    def test_classify_returns_metadata_second(self):
        """GIVEN a simple error message
        WHEN calling classify
        THEN the second element is an ErrorMetadata dict
        """
        result = classify("unknown error occurred")
        assert isinstance(result[1], dict)


class TestSyntaxClassification:
    """Test Syntax error type classification."""

    def test_unclosed_bracket(self):
        """GIVEN an error message about unclosed brackets
        WHEN classifying
        THEN it returns SYNTAX
        """
        result = classify("unclosed bracket in document")
        assert result[0] == ErrorType.SYNTAX

    def test_malformed_tag(self):
        """GIVEN an error message about malformed content
        WHEN classifying
        THEN it returns SYNTAX
        """
        result = classify("malformed XML tag at position 5")
        assert result[0] == ErrorType.SYNTAX

    def test_table_error(self):
        """GIVEN an error message about tables
        WHEN classifying
        THEN it returns SYNTAX (order test - table before asset)
        """
        result = classify("table parsing error: invalid row")
        assert result[0] == ErrorType.SYNTAX

    def test_fence_error(self):
        """GIVEN an error message about code fences
        WHEN classifying
        THEN it returns SYNTAX
        """
        result = classify("fence not closed properly")
        assert result[0] == ErrorType.SYNTAX

    def test_code_block_error(self):
        """GIVEN an error message about code blocks
        WHEN classifying
        THEN it returns SYNTAX
        """
        result = classify("code block is malformed")
        assert result[0] == ErrorType.SYNTAX


class TestEncodingClassification:
    """Test Encoding error type classification."""

    def test_encoding_error(self):
        """GIVEN an error message about encoding
        WHEN classifying
        THEN it returns ENCODING
        """
        result = classify("encoding error occurred")
        assert result[0] == ErrorType.ENCODING

    def test_utf8_error(self):
        """GIVEN an error message about UTF-8
        WHEN classifying
        THEN it returns ENCODING
        """
        result = classify("invalid utf-8 sequence")
        assert result[0] == ErrorType.ENCODING

    def test_decode_error(self):
        """GIVEN an error message about decoding
        WHEN classifying
        THEN it returns ENCODING
        """
        result = classify("failed to decode document")
        assert result[0] == ErrorType.ENCODING

    def test_unicode_error(self):
        """GIVEN an error message about unicode
        WHEN classifying
        THEN it returns ENCODING
        """
        result = classify("unicode conversion failed")
        assert result[0] == ErrorType.ENCODING


class TestAssetClassification:
    """Test Asset error type classification."""

    def test_image_error(self):
        """GIVEN an error message about images
        WHEN classifying
        THEN it returns ASSET
        """
        result = classify("image not found: logo.png")
        assert result[0] == ErrorType.ASSET

    def test_file_not_found(self):
        """GIVEN an error message about file not found
        WHEN classifying
        THEN it returns ASSET
        """
        result = classify("file not found: data.json")
        assert result[0] == ErrorType.ASSET

    def test_asset_missing(self):
        """GIVEN an error message about missing asset
        WHEN classifying
        THEN it returns ASSET
        """
        result = classify("asset missing: styles.css")
        assert result[0] == ErrorType.ASSET

    def test_enoent_error(self):
        """GIVEN an error message about ENOENT
        WHEN classifying
        THEN it returns ASSET
        """
        result = classify("ENOENT: no such file or directory")
        assert result[0] == ErrorType.ASSET


class TestStructuralClassification:
    """Test Structural error type classification."""

    def test_heading_error(self):
        """GIVEN an error message about headings
        WHEN classifying
        THEN it returns STRUCTURAL
        """
        result = classify("heading level skipped")
        assert result[0] == ErrorType.STRUCTURAL

    def test_hierarchy_error(self):
        """GIVEN an error message about hierarchy
        WHEN classifying
        THEN it returns STRUCTURAL
        """
        result = classify("hierarchy violation at line 10")
        assert result[0] == ErrorType.STRUCTURAL

    def test_level_error(self):
        """GIVEN an error message about levels
        WHEN classifying
        THEN it returns STRUCTURAL
        """
        result = classify("level mismatch in structure")
        assert result[0] == ErrorType.STRUCTURAL

    def test_skip_error(self):
        """GIVEN an error message about skipping
        WHEN classifying
        THEN it returns STRUCTURAL
        """
        result = classify("skip: invalid structure")
        assert result[0] == ErrorType.STRUCTURAL


class TestUnknownClassification:
    """Test Unknown error type classification (default)."""

    def test_unknown_error(self):
        """GIVEN an unrecognized error message
        WHEN classifying
        THEN it returns UNKNOWN
        """
        result = classify("something completely unexpected happened")
        assert result[0] == ErrorType.UNKNOWN

    def test_empty_string_unknown(self):
        """GIVEN an empty string error message
        WHEN classifying
        THEN it returns UNKNOWN
        """
        result = classify("")
        assert result[0] == ErrorType.UNKNOWN


class TestLineNumberExtraction:
    """Test line number extraction from error messages."""

    def test_line_pattern(self):
        """GIVEN an error message with 'line X' pattern
        WHEN classifying
        THEN line_number is extracted
        """
        result = classify("error at line 42")
        assert result[1]["line_number"] == 42

    def test_line_colon_pattern(self):
        """GIVEN an error message with 'line: X' pattern
        WHEN classifying
        THEN line_number is extracted
        """
        result = classify("error line: 15")
        assert result[1]["line_number"] == 15

    def test_at_line_pattern(self):
        """GIVEN an error message with 'at line X' pattern
        WHEN classifying
        THEN line_number is extracted
        """
        result = classify("malfunction at line 7")
        assert result[1]["line_number"] == 7

    def test_colon_line_colon_pattern(self):
        """GIVEN an error message with ':X:' pattern (common in parsers)
        WHEN classifying
        THEN line_number is extracted
        """
        result = classify("parse error :25: column 10")
        assert result[1]["line_number"] == 25

    def test_no_line_number(self):
        """GIVEN an error message without line number
        WHEN classifying
        THEN line_number is None
        """
        result = classify("simple error occurred")
        assert result[1]["line_number"] is None


class TestMessageTruncation:
    """Test message truncation to 2000 characters."""

    def test_long_message_truncated(self):
        """GIVEN a message longer than 2000 characters
        WHEN classifying
        THEN message is truncated to 2000 chars
        """
        long_message = "x" * 3000
        result = classify(long_message)
        assert len(result[1]["message"]) == 2000

    def test_short_message_not_truncated(self):
        """GIVEN a message shorter than 2000 characters
        WHEN classifying
        THEN message is unchanged
        """
        short_message = "short error message"
        result = classify(short_message)
        assert result[1]["message"] == short_message

    def test_exactly_2000_chars(self):
        """GIVEN a message exactly 2000 characters
        WHEN classifying
        THEN message is unchanged
        """
        exact_message = "x" * 2000
        result = classify(exact_message)
        assert len(result[1]["message"]) == 2000


class TestAssetRefExtraction:
    """Test asset_ref extraction for Asset type errors."""

    def test_asset_ref_extracted(self):
        """GIVEN an Asset error with file reference
        WHEN classifying
        THEN asset_ref is extracted
        """
        result = classify("image not found: banner.jpg")
        assert result[1].get("asset_ref") == "banner.jpg"

    def test_asset_ref_enoent(self):
        """GIVEN an ENOENT error with path
        WHEN classifying
        THEN asset_ref is extracted
        """
        result = classify("ENOENT: /path/to/document.md")
        assert result[1].get("asset_ref") == "/path/to/document.md"

    def test_asset_ref_none_for_non_asset(self):
        """GIVEN a non-Asset error
        WHEN classifying
        THEN asset_ref is None
        """
        result = classify("syntax error at line 5")
        assert result[1].get("asset_ref") is None


class TestTimestamp:
    """Test timestamp in metadata."""

    def test_timestamp_present(self):
        """GIVEN any error message
        WHEN classifying
        THEN timestamp is included in metadata
        """
        result = classify("some error")
        assert "timestamp" in result[1]

    def test_timestamp_iso8601_format(self):
        """GIVEN any error message
        WHEN classifying
        THEN timestamp is in ISO8601 format
        """
        from datetime import datetime

        result = classify("some error")
        # Should not raise - verifies ISO8601 format
        timestamp = result[1]["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
