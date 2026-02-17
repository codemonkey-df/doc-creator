from backend.error_handlers.classifier import ErrorType, ErrorMetadata, classify
from backend.error_handlers.syntax_handler import fix_unclosed_code_block
from backend.error_handlers.encoding_handler import fix_invalid_utf8
from backend.error_handlers.asset_handler import insert_placeholder
from backend.error_handlers.structural_handler import fix_heading_hierarchy

__all__ = [
    "ErrorType",
    "ErrorMetadata",
    "classify",
    "fix_unclosed_code_block",
    "fix_invalid_utf8",
    "insert_placeholder",
    "fix_heading_hierarchy",
]
