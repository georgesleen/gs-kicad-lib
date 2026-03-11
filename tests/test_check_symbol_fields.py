from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "check-symbol-fields.py"
)
SPEC = importlib.util.spec_from_file_location("check_symbol_fields", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"failed to load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CheckSymbolFieldsTests(unittest.TestCase):
    def test_missing_spice_configuration_is_warning_only(self) -> None:
        symbol = MODULE.Symbol(
            name="TestPart",
            path=Path("symbols/Test.kicad_sym"),
            in_bom=True,
            properties={
                "Reference": MODULE.Property("U", False),
                "Value": MODULE.Property("TestPart", False),
                "Footprint": MODULE.Property("GS_SO:SOT-23", True),
                "Datasheet": MODULE.Property("~", True),
                "Description": MODULE.Property("test part", True),
                "Manufacturer": MODULE.Property("Test", True),
                "Mfr. Part #": MODULE.Property("TEST-1", True),
                "LCSC ID": MODULE.Property("C1", True),
                "Package": MODULE.Property("SOT-23", True),
            },
        )

        issues, warnings = MODULE.validate_symbol(symbol)

        self.assertEqual(issues, [])
        self.assertEqual(warnings, ["no SPICE model configured"])

    def test_spice_warning_override_suppresses_warning(self) -> None:
        symbol = MODULE.Symbol(
            name="TestPart",
            path=Path("symbols/Test.kicad_sym"),
            in_bom=True,
            properties={
                "Reference": MODULE.Property("U", False),
                "Value": MODULE.Property("TestPart", False),
                "Footprint": MODULE.Property("GS_SO:SOT-23", True),
                "Datasheet": MODULE.Property("~", True),
                "Description": MODULE.Property("test part", True),
                "Manufacturer": MODULE.Property("Test", True),
                "Mfr. Part #": MODULE.Property("TEST-1", True),
                "LCSC ID": MODULE.Property("C1", True),
                "Package": MODULE.Property("SOT-23", True),
                "SPICE Warning Override": MODULE.Property("digital-only symbol", True),
            },
        )

        issues, warnings = MODULE.validate_symbol(symbol)

        self.assertEqual(issues, [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
