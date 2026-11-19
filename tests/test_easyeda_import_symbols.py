from __future__ import annotations

import pytest

from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.paths import block_depth_delta
from kicad_lib_tools.symbols import (
    parse_property_block,
    parse_symbol_properties,
    rename_symbol,
    sanitize_symbol_name,
)


def test_block_depth_ignores_parentheses_in_strings() -> None:
    line = '(property "Description" "Buck regulator (3A)" (id 0))'
    assert block_depth_delta(line) == 0


def test_parse_multiline_property_blocks() -> None:
    symbol_text = """\
(symbol "DZDH0401DW-7"
  (property
    "Reference"
    "U"
    (id 0)
    (at 0 7.62 0)
    (effects (font (size 1.27 1.27)))
  )
  (property
    "Datasheet"
    "https://www.lcsc.com/datasheet/C3235552.pdf"
    (id 3)
    (at 0 -12.70 0)
    (effects (font (size 1.27 1.27)) hide)
  )
)
"""
    properties = {prop.name: prop for prop in parse_symbol_properties(symbol_text)}

    assert properties["Reference"].value == "U"
    assert not properties["Reference"].hidden
    assert properties["Datasheet"].value == "https://www.lcsc.com/datasheet/C3235552.pdf"
    assert properties["Datasheet"].hidden


def test_parse_property_block_rejects_unparseable_text() -> None:
    with pytest.raises(ImportErrorWithExitCode, match="failed to parse property block"):
        parse_property_block(["(property\n", "  (id 0)\n", ")\n"], 0)


def test_sanitize_symbol_name_replaces_slashes_and_spaces() -> None:
    assert sanitize_symbol_name(" TYPE-C 6P/QT ") == "TYPE-C_6P_QT"


def test_rename_symbol_renames_block_and_unit_symbols_only() -> None:
    block = (
        '(symbol "AO3415"\n'
        '\t(property "Value" "AO3415")\n'
        '\t(symbol "AO3415_0_1")\n'
        '\t(symbol "AO3415_1_1")\n'
        '\t(symbol "AO3415A_1_1")\n'
        ")\n"
    )
    assert rename_symbol(block, "AO3415", "MOSFET_P-Ch") == (
        '(symbol "MOSFET_P-Ch"\n'
        '\t(property "Value" "AO3415")\n'
        '\t(symbol "MOSFET_P-Ch_0_1")\n'
        '\t(symbol "MOSFET_P-Ch_1_1")\n'
        '\t(symbol "AO3415A_1_1")\n'
        ")\n"
    )
