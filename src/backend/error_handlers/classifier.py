"""Error Classifier - Classifies error messages into types."""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import TypedDict


class ErrorType(Enum):
    """Error type classification categories."""

    SYNTAX = "syntax"
    ENCODING = "encoding"
    ASSET = "asset"
    STRUCTURAL = "structural"
    UNKNOWN = "unknown"


class ErrorMetadata(TypedDict, total=False):
    """Metadata for classified errors."""

    line_number: int | None
    message: str
    timestamp: str
    context: str | None
    source: str | None
    asset_ref: str | None


# Keyword patterns for each error type (canonical evaluation order)
SYNTAX_KEYWORDS = ["unclosed", "malformed", "table", "fence", "code block"]
ENCODING_KEYWORDS = ["encoding", "utf-8", "decode", "unicode"]
ASSET_KEYWORDS = ["image", "file not found", "asset", "missing", "enoent"]
STRUCTURAL_KEYWORDS = ["heading", "hierarchy", "level", "skip"]

# Regex patterns for line number extraction
LINE_NUMBER_PATTERNS = [
    re.compile(r"line\s+(\d+)", re.IGNORECASE),
    re.compile(r"line:\s*(\d+)", re.IGNORECASE),
    re.compile(r"at\s+line\s+(\d+)", re.IGNORECASE),
    re.compile(r":(\d+):"),  # Common parser format: :25: column 10
]

# Regex pattern for asset reference extraction
ASSET_REF_PATTERN = re.compile(
    r"(?:not found|missing|ENOENT)[:\s]+(.+)$", re.IGNORECASE
)

MAX_MESSAGE_LENGTH = 2000


def _extract_line_number(message: str) -> int | None:
    """Extract line number from error message using multiple patterns."""
    for pattern in LINE_NUMBER_PATTERNS:
        match = pattern.search(message)
        if match:
            return int(match.group(1))
    return None


def _extract_asset_ref(message: str) -> str | None:
    """Extract asset reference from error message."""
    match = ASSET_REF_PATTERN.search(message)
    if match:
        return match.group(1).strip()
    return None


def _contains_keyword(message_lower: str, keywords: list[str]) -> bool:
    """Check if message contains any of the keywords."""
    return any(keyword in message_lower for keyword in keywords)


def classify(error_msg: str) -> tuple[ErrorType, ErrorMetadata]:
    """Classify an error message into an ErrorType with metadata.

    Args:
        error_msg: The error message to classify

    Returns:
        Tuple of (ErrorType, ErrorMetadata)
    """
    # Handle empty string
    if not error_msg:
        return (
            ErrorType.UNKNOWN,
            ErrorMetadata(
                line_number=None,
                message="",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    message_lower = error_msg.lower()
    truncated_message = error_msg[:MAX_MESSAGE_LENGTH]

    # Extract line number
    line_number = _extract_line_number(error_msg)

    # Canonical evaluation order: Syntax -> Encoding -> Asset -> Structural -> Unknown

    # Syntax
    if _contains_keyword(message_lower, SYNTAX_KEYWORDS):
        return (
            ErrorType.SYNTAX,
            ErrorMetadata(
                line_number=line_number,
                message=truncated_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    # Encoding
    if _contains_keyword(message_lower, ENCODING_KEYWORDS):
        return (
            ErrorType.ENCODING,
            ErrorMetadata(
                line_number=line_number,
                message=truncated_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    # Asset (also extract asset_ref)
    if _contains_keyword(message_lower, ASSET_KEYWORDS):
        asset_ref = _extract_asset_ref(error_msg)
        return (
            ErrorType.ASSET,
            ErrorMetadata(
                line_number=line_number,
                message=truncated_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
                asset_ref=asset_ref,
            ),
        )

    # Structural
    if _contains_keyword(message_lower, STRUCTURAL_KEYWORDS):
        return (
            ErrorType.STRUCTURAL,
            ErrorMetadata(
                line_number=line_number,
                message=truncated_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    # Unknown (default)
    return (
        ErrorType.UNKNOWN,
        ErrorMetadata(
            line_number=line_number,
            message=truncated_message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )
