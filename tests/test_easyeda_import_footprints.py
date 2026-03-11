from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.easyeda_import.footprints import parse_footprint_name


class ParseFootprintNameTests(unittest.TestCase):
    def test_parses_kicad_v6_footprint_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            footprint_path = Path(tmp_dir) / "part.kicad_mod"
            footprint_path.write_text(
                '(footprint "MyLib:USB_C_Receptacle"\n)\n',
                encoding="utf-8",
            )

            self.assertEqual(parse_footprint_name(footprint_path), "USB_C_Receptacle")

    def test_parses_legacy_module_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            footprint_path = Path(tmp_dir) / "part.kicad_mod"
            footprint_path.write_text(
                "(module easyeda2kicad:SOT-363_L2.0-W1.3-P0.65-LS2.1-BR (layer F.Cu)\n)\n",
                encoding="utf-8",
            )

            self.assertEqual(
                parse_footprint_name(footprint_path),
                "SOT-363_L2.0-W1.3-P0.65-LS2.1-BR",
            )


if __name__ == "__main__":
    unittest.main()
