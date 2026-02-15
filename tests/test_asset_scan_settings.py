"""
Test suite for AssetScanSettings (Story 3.1: Asset Scan Node).

Tests cover:
- Default configuration
- Environment variable loading
- Path validation
"""

import os
from pathlib import Path

import pytest

from src.backend.utils.settings import AssetScanSettings


class TestAssetScanSettingsDefaults:
    """Tests for default AssetScanSettings values."""

    def test_allowed_base_path_defaults_to_none(self) -> None:
        """GIVEN no env var / WHEN AssetScanSettings created / THEN allowed_base_path is None."""
        # Clear env var if set
        os.environ.pop("ASSET_ALLOWED_BASE_PATH", None)

        settings = AssetScanSettings()

        assert settings.allowed_base_path is None

    def test_settings_instantiation_success(self) -> None:
        """GIVEN valid settings / WHEN instantiated / THEN no error."""
        settings = AssetScanSettings(allowed_base_path=None)

        assert settings is not None
        assert isinstance(settings, AssetScanSettings)


class TestAssetScanSettingsEnvLoading:
    """Tests for loading AssetScanSettings from environment."""

    def test_load_allowed_base_path_from_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GIVEN ASSET_ALLOWED_BASE_PATH env var / WHEN loaded / THEN used."""
        # Create a test directory
        base_path = tmp_path / "test_base"
        base_path.mkdir()

        # Set env var
        monkeypatch.setenv("ASSET_ALLOWED_BASE_PATH", str(base_path))

        settings = AssetScanSettings()

        assert settings.allowed_base_path is not None
        assert settings.allowed_base_path == base_path

    def test_load_allowed_base_path_as_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GIVEN ASSET_ALLOWED_BASE_PATH as string path / WHEN loaded / THEN converted to Path."""
        base_path = tmp_path / "test_base"
        base_path.mkdir()

        monkeypatch.setenv("ASSET_ALLOWED_BASE_PATH", str(base_path))

        settings = AssetScanSettings()

        assert isinstance(settings.allowed_base_path, Path)
        assert settings.allowed_base_path == Path(str(base_path))

    def test_env_var_prefix_asset(self) -> None:
        """GIVEN env prefix ASSET_ / WHEN checked / THEN correct."""
        # Verify the settings model uses ASSET_ prefix
        assert AssetScanSettings.model_config["env_prefix"] == "ASSET_"


class TestAssetScanSettingsValidation:
    """Tests for AssetScanSettings validation."""

    def test_allowed_base_path_none_is_valid(self) -> None:
        """GIVEN allowed_base_path is None / WHEN validated / THEN valid."""
        settings = AssetScanSettings(allowed_base_path=None)

        assert settings.allowed_base_path is None

    def test_allowed_base_path_existing_directory(self, tmp_path: Path) -> None:
        """GIVEN allowed_base_path is existing directory / WHEN validated / THEN valid."""
        base_dir = tmp_path / "existing"
        base_dir.mkdir()

        settings = AssetScanSettings(allowed_base_path=base_dir)

        assert settings.allowed_base_path == base_dir

    def test_allowed_base_path_relative_path(self, tmp_path: Path) -> None:
        """GIVEN allowed_base_path as relative Path / WHEN set / THEN stored."""
        # Pydantic accepts Path objects; they're stored as-is
        rel_path = Path("./relative/path")

        settings = AssetScanSettings(allowed_base_path=rel_path)

        assert settings.allowed_base_path == rel_path

    def test_allowed_base_path_absolute_path(self, tmp_path: Path) -> None:
        """GIVEN allowed_base_path as absolute Path / WHEN set / THEN stored."""
        abs_path = tmp_path / "absolute"
        abs_path.mkdir()

        settings = AssetScanSettings(allowed_base_path=abs_path)

        assert settings.allowed_base_path == abs_path
        assert settings.allowed_base_path.is_absolute()
