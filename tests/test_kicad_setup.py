"""Tests for KiCad library registration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kicad_lib_tools import kicad_setup as _setup
from kicad_lib_tools.config import LibraryConfig

# ---------------------------------------------------------------------------
# library_description
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lib_type, lib_name, expected",
    [
        ("symbol", "GS_IC", "integrated circuit symbol library"),
        ("symbol", "GS_PMIC", "PMIC symbol library"),
        ("symbol", "GS_MCU", "microcontroller symbol library"),
        ("symbol", "GS_Diodes", "discrete diodes and rectifiers symbol library"),
        ("symbol", "GS_Resistor_0402", "0402 resistor symbol library"),
        ("symbol", "GS_Capacitor_0603", "0603 capacitor symbol library"),
        ("footprint", "GS_Connectors", "connectors footprint library"),
        ("footprint", "GS_Resistor_0402", "0402 resistor footprint library"),
    ],
)
def test_library_description(lib_type: str, lib_name: str, expected: str) -> None:
    assert _setup.library_description(lib_type, lib_name, "GS") == expected


# ---------------------------------------------------------------------------
# upsert_lib_entry
# ---------------------------------------------------------------------------


def test_upsert_adds_new_entry(tmp_path: Path) -> None:
    table = tmp_path / "sym-lib-table"
    table.write_text("(sym_lib_table\n)\n", encoding="utf-8")
    _setup.upsert_lib_entry(table, "GS_IC", "${GS_SYMBOL_DIR}/GS_IC.kicad_sym", "IC lib")
    content = table.read_text()
    assert '(name "GS_IC")' in content
    assert content.strip().endswith(")")


def test_upsert_replaces_existing_entry(tmp_path: Path) -> None:
    table = tmp_path / "sym-lib-table"
    table.write_text(
        "(sym_lib_table\n"
        '  (lib (name "GS_IC")(type "KiCad")(uri "old")(options "")(descr "old"))\n'
        ")\n",
        encoding="utf-8",
    )
    _setup.upsert_lib_entry(table, "GS_IC", "${GS_SYMBOL_DIR}/GS_IC.kicad_sym", "new desc")
    content = table.read_text()
    assert content.count('(name "GS_IC")') == 1
    assert "new desc" in content
    assert "old" not in content


def test_upsert_does_not_corrupt_other_entries(tmp_path: Path) -> None:
    table = tmp_path / "sym-lib-table"
    table.write_text(
        "(sym_lib_table\n"
        '  (lib (name "GS_Other")(type "KiCad")(uri "x")(options "")(descr "d"))\n'
        ")\n",
        encoding="utf-8",
    )
    _setup.upsert_lib_entry(table, "GS_IC", "${GS_SYMBOL_DIR}/GS_IC.kicad_sym", "IC lib")
    content = table.read_text()
    assert '(name "GS_Other")' in content
    assert '(name "GS_IC")' in content


# ---------------------------------------------------------------------------
# update_kicad_common
# ---------------------------------------------------------------------------


def test_update_kicad_common_creates_file(tmp_path: Path) -> None:
    f = tmp_path / "kicad_common.json"
    _setup.update_kicad_common(f, {"GS_SYMBOL_DIR": "/sym"})
    data = json.loads(f.read_text())
    assert data["environment"]["vars"]["GS_SYMBOL_DIR"] == "/sym"


def test_update_kicad_common_merges_existing(tmp_path: Path) -> None:
    f = tmp_path / "kicad_common.json"
    f.write_text(json.dumps({"environment": {"vars": {"OTHER": "x"}}}), encoding="utf-8")
    _setup.update_kicad_common(f, {"GS_SYMBOL_DIR": "/sym"})
    data = json.loads(f.read_text())
    assert data["environment"]["vars"]["OTHER"] == "x"
    assert data["environment"]["vars"]["GS_SYMBOL_DIR"] == "/sym"


def test_update_kicad_common_handles_corrupt_json(tmp_path: Path) -> None:
    f = tmp_path / "kicad_common.json"
    f.write_text("not json", encoding="utf-8")
    _setup.update_kicad_common(f, {"GS_SYMBOL_DIR": "/sym"})
    data = json.loads(f.read_text())
    assert data["environment"]["vars"]["GS_SYMBOL_DIR"] == "/sym"


def test_register_libraries_uses_prefix_path_variables(tmp_path: Path) -> None:
    config = LibraryConfig(repo_root=tmp_path / "lib", library_prefix="ACME")
    config.symbol_path.mkdir(parents=True)
    config.footprint_path.mkdir()
    (config.symbol_path / "ACME_Diodes.kicad_sym").write_text("(kicad_symbol_lib)\n")
    kicad_dir = tmp_path / "kicad"

    _setup.register_libraries(config, kicad_dir)

    table = (kicad_dir / "sym-lib-table").read_text()
    assert '(uri "${ACME_SYMBOL_DIR}/ACME_Diodes.kicad_sym")' in table
    assert '(descr "discrete diodes and rectifiers symbol library")' in table
    env = json.loads((kicad_dir / "kicad_common.json").read_text())["environment"]["vars"]
    assert env["ACME_3DMODEL_DIR"] == str(config.model_path)


def test_register_libraries_rejects_missing_library_directories(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _setup.register_libraries(LibraryConfig(repo_root=tmp_path), tmp_path / "kicad")
