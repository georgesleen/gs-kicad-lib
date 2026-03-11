from __future__ import annotations

import pytest

from scripts.easyeda_import.errors import ImportErrorWithExitCode
from scripts.easyeda_import.paths import block_depth_delta
from scripts.easyeda_import.symbols import parse_property_block, parse_symbol_properties


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
