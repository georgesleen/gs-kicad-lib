"""Tests for scripts/setup-kicad.py logic functions."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_setup() -> Any:
    spec = importlib.util.spec_from_file_location("_setup_kicad", SCRIPTS_DIR / "setup-kicad.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(spec.name, None)
    return mod


_setup = _load_setup()


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
    assert _setup.library_description(lib_type, lib_name) == expected


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
