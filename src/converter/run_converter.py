"""DOCX converter wrapper module."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class ConverterError(Exception):
    """Exception raised when DOCX conversion fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _find_node_executable() -> str:
    """Find the Node.js executable to use.

    Returns:
        Path to node executable.

    Raises:
        ConverterError: If node is not installed.
    """
    # Check for NODE_PATH environment variable override
    node_path = os.environ.get("NODE_PATH")
    if node_path and shutil.which(node_path):
        return node_path

    # Check if 'node' is available in PATH
    node_executable = shutil.which("node")
    if node_executable:
        return node_executable

    raise ConverterError(
        "Node.js is not installed or not found in PATH. Please install Node.js to convert to DOCX."
    )


def _get_converter_script_path() -> Path:
    """Get the path to converter/convert.js relative to this file.

    Returns:
        Path to converter/convert.js
    """
    # This file is at src/converter/run_converter.py
    # converter/ is at the project root
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent
    converter_script = project_root / "converter" / "convert.js"
    return converter_script


def convert_to_docx(markdown_path: Path, title: str, output_path: Path) -> Path:
    """Convert markdown file to DOCX using the Node.js converter.

    Args:
        markdown_path: Path to the input markdown file.
        title: Document title.
        output_path: Path where the output DOCX should be written.

    Returns:
        Path to the created DOCX file.

    Raises:
        ConverterError: If conversion fails.
    """
    # Find node executable
    node_executable = _find_node_executable()

    # Get converter script path
    converter_script = _get_converter_script_path()

    if not converter_script.exists():
        raise ConverterError(
            f"Converter script not found at {converter_script}. Please ensure converter/convert.js exists."
        )

    # Build command
    cmd = [
        node_executable,
        str(converter_script),
        str(markdown_path),
        "--title",
        title,
        "--output",
        str(output_path),
    ]

    # Run conversion
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )
    except TimeoutError as e:
        raise ConverterError(f"Conversion timed out: {e}") from e

    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        logger.error("converter_failed", extra={"error": error_msg})
        raise ConverterError(error_msg)

    logger.info("converter_success", extra={"output_path": str(output_path)})
    return output_path
