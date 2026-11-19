from __future__ import annotations

from pathlib import Path

import pytest

from kicad_lib_tools.config import LibraryConfig
from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.libraries import (
    create_symbol_library,
    ensure_footprint_library,
    ensure_symbol_library,
    find_symbols_by_lcsc_id,
    list_library_symbols,
    normalize_library_name,
    suggest_library,
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
    repo: LibraryConfig,
) -> None:
    path = repo.symbol_path / "GS_New.kicad_sym"
    with pytest.raises(ImportErrorWithExitCode, match="symbol library does not exist"):
        ensure_symbol_library(path, interactive=False)


def test_ensure_footprint_library_rejects_missing_library_non_interactive(
    repo: LibraryConfig,
) -> None:
    path = repo.footprint_path / "GS_New.pretty"
    with pytest.raises(ImportErrorWithExitCode, match="footprint library does not exist"):
        ensure_footprint_library(path, interactive=False)


def test_ensure_symbol_library_returns_false_when_library_exists(
    tmp_path: Path,
) -> None:
    path = tmp_path / "symbols" / "GS_Existing.kicad_sym"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    assert ensure_symbol_library(path, interactive=False) is False


def test_create_symbol_library_writes_expected_header(tmp_path: Path) -> None:
    path = tmp_path / "symbols" / "GS_Test.kicad_sym"
    create_symbol_library(path)
    assert path.read_text(encoding="utf-8") == (
        "(kicad_symbol_lib\n"
        "\t(version 20241209)\n"
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "9.0")\n'
        ")\n"
    )


SYMBOL_LIBRARIES = [
    "GS_Capacitor_0402",
    "GS_Connectors",
    "GS_IC",
    "GS_Optoelectronic",
    "GS_Switching_Regulators",
]


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("Connectors USB, DVI, HDMI Connector Assemblies", "GS_Connectors"),
        ("Optoelectronics Light Emitting Diodes (LED)", "GS_Optoelectronic"),
        ("Power Management ICs Switching Regulators", "GS_Switching_Regulators"),
        ("Capacitors Multilayer Ceramic Capacitors MLCC - SMD/SMT", None),
        ("", None),
    ],
)
def test_suggest_library_matches_category_words(category: str, expected: str | None) -> None:
    assert suggest_library(category, SYMBOL_LIBRARIES) == expected


def write_library(path: Path, symbols: dict[str, str]) -> Path:
    blocks = "".join(
        f'\t(symbol "{name}"\n\t\t(property "LCSC ID" "{lcsc}"\n\t\t)\n\t)\n'
        for name, lcsc in symbols.items()
    )
    path.write_text(f"(kicad_symbol_lib\n{blocks})\n", encoding="utf-8")
    return path


def test_find_symbols_by_lcsc_id_lists_every_match(tmp_path: Path) -> None:
    first = write_library(tmp_path / "GS_A.kicad_sym", {"USB_C": "C165948", "JST": "C1"})
    second = write_library(tmp_path / "GS_B.kicad_sym", {"USB_C_Alt": "C165948"})
    assert find_symbols_by_lcsc_id("C165948", [first, second]) == [
        "GS_A:USB_C",
        "GS_B:USB_C_Alt",
    ]
    assert find_symbols_by_lcsc_id("C2", [first, second]) == []


def test_list_library_symbols_reads_names_in_file_order(repo: LibraryConfig) -> None:
    write_library(repo.symbol_path / "GS_A.kicad_sym", {"Zeta": "C1", "Alpha": "C2"})
    assert list_library_symbols("GS_A") == ["Zeta", "Alpha"]
    assert list_library_symbols("GS_Missing") == []
