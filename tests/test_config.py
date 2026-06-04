"""Tests for LibraryConfig boundary validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from kicad_lib_tools.config import LibraryConfig


def _base(tmp_path: Path, **overrides: str) -> LibraryConfig:
    kwargs: dict[str, object] = {
        "repo_root": tmp_path,
        "library_prefix": "GS",
        "symbol_dir": "symbols",
        "footprint_dir": "footprints",
        "model_dir": "3d-models",
    }
    kwargs.update(overrides)
    return LibraryConfig(**kwargs)  # type: ignore[arg-type]


def test_valid_config_constructs(tmp_path: Path) -> None:
    cfg = _base(tmp_path)
    assert cfg.library_prefix == "GS"


def test_empty_library_prefix_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="library_prefix"):
        _base(tmp_path, library_prefix="")


def test_empty_symbol_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="symbol_dir"):
        _base(tmp_path, symbol_dir="")


def test_empty_footprint_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="footprint_dir"):
        _base(tmp_path, footprint_dir="")


def test_empty_model_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_dir"):
        _base(tmp_path, model_dir="")
