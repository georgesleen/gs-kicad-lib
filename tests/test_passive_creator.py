from __future__ import annotations

from pathlib import Path

import pytest

from kicad_lib_tools.lcsc_api import LCSCPart
from kicad_lib_tools.passive_creator import (
    build_derived_symbol_block,
    build_description,
    build_symbol_name,
    determine_library_name,
    find_base_symbol,
    normalize_capacitance,
    normalize_resistance,
    normalize_value,
)
from kicad_lib_tools.symbols import SymbolBlock


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("5.1kΩ", "5.1k"),
        ("100Ω", "100R"),
        ("4.7MΩ", "4.7M"),
        ("10kΩ", "10k"),
        ("0Ω", "0R"),
        ("1.5k", "1.5k"),
        (" 47k ", "47k"),
    ],
)
def test_normalize_resistance(raw: str, expected: str) -> None:
    assert normalize_resistance(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("100nF", "100nF"),
        ("10µF", "10uF"),
        ("22pF", "22pF"),
        (" 4.7µF ", "4.7uF"),
    ],
)
def test_normalize_capacitance(raw: str, expected: str) -> None:
    assert normalize_capacitance(raw) == expected


def test_normalize_value_dispatches_by_category() -> None:
    assert normalize_value("10kΩ", "Resistors") == "10k"
    assert normalize_value("100nF", "Capacitors") == "100nF"
    assert normalize_value("some value", "Other") == "some value"


# ---------------------------------------------------------------------------
# Symbol & library naming
# ---------------------------------------------------------------------------


def test_build_symbol_name() -> None:
    assert build_symbol_name("Resistors", "0603", "10k") == "R_0603_10k"
    assert build_symbol_name("Capacitors", "0805", "100nF") == "C_0805_100nF"


def test_determine_library_name() -> None:
    assert determine_library_name("Resistors", "0603") == "GS_Resistor_0603"
    assert determine_library_name("Capacitors", "0402") == "GS_Capacitor_0402"


def test_determine_library_name_rejects_unknown_category() -> None:
    from kicad_lib_tools.errors import ImportErrorWithExitCode

    with pytest.raises(ImportErrorWithExitCode):
        determine_library_name("Inductors", "0603")


# ---------------------------------------------------------------------------
# Description builders
# ---------------------------------------------------------------------------


def _make_part(**kwargs) -> LCSCPart:
    defaults = dict(
        lcsc_id="C1",
        manufacturer="Test",
        mpn="TEST-1",
        description="test",
        datasheet_url="",
        package="0603",
        category="",
        parent_category="Resistors",
        attributes={},
    )
    defaults.update(kwargs)
    return LCSCPart(**defaults)


def test_build_resistor_description() -> None:
    part = _make_part(
        parent_category="Resistors",
        attributes={
            "Tolerance": "±1%",
            "Power": "100mW",
            "Voltage Rating": "75V",
            "Temperature Coefficient": "±100ppm/℃",
        },
    )
    desc = build_description(part, "10k")
    assert desc == "10k 1% Resistor, 100mW Max Power, 75V Max Voltage, 100ppm"


def test_build_capacitor_description() -> None:
    part = _make_part(
        parent_category="Capacitors",
        attributes={
            "Tolerance": "±10%",
            "Voltage Rating": "50V",
            "Temperature Coefficient": "X7R",
        },
    )
    desc = build_description(part, "100nF")
    assert desc == "100nF 10% Unpolarized Capacitor, 50V Max Voltage, X7R"


# ---------------------------------------------------------------------------
# find_base_symbol
# ---------------------------------------------------------------------------


def test_find_base_symbol(tmp_path: Path) -> None:
    lib = tmp_path / "GS_Test.kicad_sym"
    lib.write_text(
        '(kicad_symbol_lib\n'
        '\t(version 20241209)\n'
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "9.0")\n'
        '\t(symbol "R_Base"\n'
        '\t\t(pin_numbers (hide yes))\n'
        '\t\t(pin_names (offset 0))\n'
        '\t\t(exclude_from_sim no)\n'
        '\t\t(in_bom yes)\n'
        '\t\t(on_board yes)\n'
        '\t\t(property "Reference" "R"\n'
        '\t\t\t(at 0 0 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t)\n'
        '\t\t(property "Value" "Base"\n'
        '\t\t\t(at 0 0 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t)\n'
        '\t\t(symbol "R_Base_0_1"\n'
        '\t\t\t(polyline (pts (xy 0 1) (xy 0 -1)) (stroke (width 0) (type default)) (fill (type none)))\n'
        '\t\t)\n'
        '\t\t(symbol "R_Base_1_1"\n'
        '\t\t\t(pin passive line (at 0 2 270) (length 1) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))\n'
        '\t\t)\n'
        '\t\t(embedded_fonts no)\n'
        '\t)\n'
        '\t(symbol "R_Derived"\n'
        '\t\t(extends "R_Base")\n'
        '\t\t(property "Reference" "R"\n'
        '\t\t\t(at 0 0 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t)\n'
        '\t\t(property "Value" "Derived"\n'
        '\t\t\t(at 0 0 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t)\n'
        '\t\t(embedded_fonts no)\n'
        '\t)\n'
        ')\n',
        encoding="utf-8",
    )

    base = find_base_symbol(lib)
    assert base.name == "R_Base"


# ---------------------------------------------------------------------------
# build_derived_symbol_block
# ---------------------------------------------------------------------------


def test_build_derived_symbol_block() -> None:
    base_text = (
        '\t(symbol "R_0603_5.1k"\n'
        '\t\t(pin_numbers (hide yes))\n'
        '\t\t(pin_names (offset 0))\n'
        '\t\t(exclude_from_sim no)\n'
        '\t\t(in_bom yes)\n'
        '\t\t(on_board yes)\n'
        '\t\t(property "Reference" "R"\n'
        '\t\t\t(at 2.54 0 90)\n'
        '\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t)\n'
        '\t\t(property "Value" "5.1k"\n'
        '\t\t\t(at -2.54 0 90)\n'
        '\t\t\t(effects (font (size 1.27 1.27)))\n'
        '\t\t)\n'
        '\t\t(property "Manufacturer" "UNI-ROYAL"\n'
        '\t\t\t(at 0 0 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        '\t\t)\n'
        '\t\t(property "LCSC ID" "C23186"\n'
        '\t\t\t(at 0 0 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        '\t\t)\n'
        '\t\t(symbol "R_0603_5.1k_0_1"\n'
        '\t\t\t(polyline (pts (xy 0 1) (xy 0 -1)) (stroke (width 0) (type default)) (fill (type none)))\n'
        '\t\t)\n'
        '\t\t(embedded_fonts no)\n'
        '\t)\n'
    )
    base = SymbolBlock(name="R_0603_5.1k", start=0, end=0, text=base_text)

    result = build_derived_symbol_block(
        base_symbol=base,
        new_name="R_0603_10k",
        overrides={
            "Value": "10k",
            "Manufacturer": "YAGEO",
            "LCSC ID": "C99999",
        },
    )

    assert '(symbol "R_0603_10k"' in result
    assert '(extends "R_0603_5.1k")' in result
    assert '"Value" "10k"' in result
    assert '"Manufacturer" "YAGEO"' in result
    assert '"LCSC ID" "C99999"' in result
    # Position preserved from base
    assert "(at 2.54 0 90)" in result  # Reference position
    assert "(at -2.54 0 90)" in result  # Value position
    assert "(embedded_fonts no)" in result
    # No graphical sub-symbols
    assert "R_0603_10k_0_1" not in result
