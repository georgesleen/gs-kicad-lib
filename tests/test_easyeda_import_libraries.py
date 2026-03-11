from __future__ import annotations

from pathlib import Path

import pytest

from scripts.easyeda_import.errors import ImportErrorWithExitCode
from scripts.easyeda_import.libraries import (
    create_symbol_library,
    ensure_footprint_library,
    ensure_symbol_library,
    normalize_library_name,
)


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("GS_IC", "GS_IC"),
        ("GS_IC.kicad_sym", "GS_IC"),
        ("GS_IC.pretty", "GS_IC"),
        (" GS_Power ", "GS_Power"),
    ],
)
def test_normalize_library_name_accepts_repo_names(raw_name: str, expected: str) -> None:
    assert normalize_library_name(raw_name) == expected


@pytest.mark.parametrize("raw_name", ["IC", "gs_ic", "GS-IC", "GS_"])
def test_normalize_library_name_rejects_invalid_names(raw_name: str) -> None:
    with pytest.raises(ImportErrorWithExitCode, match="invalid library name"):
        normalize_library_name(raw_name)


def test_ensure_symbol_library_rejects_missing_library_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.easyeda_import.libraries.REPO_ROOT", tmp_path)
    path = tmp_path / "symbols" / "GS_New.kicad_sym"
    with pytest.raises(ImportErrorWithExitCode, match="symbol library does not exist"):
        ensure_symbol_library(path, interactive=False)


def test_ensure_footprint_library_rejects_missing_library_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.easyeda_import.libraries.REPO_ROOT", tmp_path)
    path = tmp_path / "footprints" / "GS_New.pretty"
    with pytest.raises(ImportErrorWithExitCode, match="footprint library does not exist"):
        ensure_footprint_library(path, interactive=False)


def test_ensure_symbol_library_returns_false_when_library_exists(tmp_path: Path) -> None:
    path = tmp_path / "symbols" / "GS_Existing.kicad_sym"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    assert ensure_symbol_library(path, interactive=False) is False


def test_create_symbol_library_writes_expected_header(tmp_path: Path) -> None:
    path = tmp_path / "symbols" / "GS_Test.kicad_sym"
    create_symbol_library(path)
    assert path.read_text(encoding="utf-8") == (
        "(kicad_symbol_lib\n"
        '\t(version 20241209)\n'
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "9.0")\n'
        ")\n"
    )
