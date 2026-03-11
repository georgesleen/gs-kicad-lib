from __future__ import annotations

import unittest

from scripts.easyeda_import.paths import block_depth_delta
from scripts.easyeda_import.symbols import parse_symbol_properties


class SymbolParsingTests(unittest.TestCase):
    def test_block_depth_ignores_parentheses_in_strings(self) -> None:
        line = '(property "Description" "Buck regulator (3A)" (id 0))'
        self.assertEqual(block_depth_delta(line), 0)

    def test_parse_multiline_property_blocks(self) -> None:
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

        self.assertEqual(properties["Reference"].value, "U")
        self.assertFalse(properties["Reference"].hidden)
        self.assertEqual(
            properties["Datasheet"].value,
            "https://www.lcsc.com/datasheet/C3235552.pdf",
        )
        self.assertTrue(properties["Datasheet"].hidden)


if __name__ == "__main__":
    unittest.main()
