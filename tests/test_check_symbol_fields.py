from __future__ import annotations

from pathlib import Path


def test_missing_spice_configuration_is_warning_only(check_symbol_fields_module) -> None:
    symbol = check_symbol_fields_module.Symbol(
        name="TestPart",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        pin_count=3,
        extends=None,
        properties={
            "Reference": check_symbol_fields_module.Property("U", False),
            "Value": check_symbol_fields_module.Property("TestPart", False),
            "Footprint": check_symbol_fields_module.Property("GS_SO:SOT-23", True),
            "Datasheet": check_symbol_fields_module.Property("~", True),
            "Description": check_symbol_fields_module.Property("test part", True),
            "Manufacturer": check_symbol_fields_module.Property("Test", True),
            "Mfr. Part #": check_symbol_fields_module.Property("TEST-1", True),
            "LCSC ID": check_symbol_fields_module.Property("C1", True),
            "Package": check_symbol_fields_module.Property("SOT-23", True),
        },
    )

    issues, warnings = check_symbol_fields_module.validate_symbol(symbol)

    assert issues == []
    assert warnings == ["no SPICE model configured"]


def test_spice_warning_override_suppresses_warning(check_symbol_fields_module) -> None:
    symbol = check_symbol_fields_module.Symbol(
        name="TestPart",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        pin_count=3,
        extends=None,
        properties={
            "Reference": check_symbol_fields_module.Property("U", False),
            "Value": check_symbol_fields_module.Property("TestPart", False),
            "Footprint": check_symbol_fields_module.Property("GS_SO:SOT-23", True),
            "Datasheet": check_symbol_fields_module.Property("~", True),
            "Description": check_symbol_fields_module.Property("test part", True),
            "Manufacturer": check_symbol_fields_module.Property("Test", True),
            "Mfr. Part #": check_symbol_fields_module.Property("TEST-1", True),
            "LCSC ID": check_symbol_fields_module.Property("C1", True),
            "Package": check_symbol_fields_module.Property("SOT-23", True),
            "SPICE Warning Override": check_symbol_fields_module.Property(
                "digital-only symbol",
                True,
            ),
        },
    )

    issues, warnings = check_symbol_fields_module.validate_symbol(symbol)

    assert issues == []
    assert warnings == []


def test_inferred_passive_model_suppresses_warning(check_symbol_fields_module) -> None:
    symbol = check_symbol_fields_module.Symbol(
        name="R_Test",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        pin_count=2,
        extends=None,
        properties={
            "Reference": check_symbol_fields_module.Property("R", False),
            "Value": check_symbol_fields_module.Property("10k", False),
            "Footprint": check_symbol_fields_module.Property(
                "GS_Resistors:R_0603_1608Metric",
                True,
            ),
            "Datasheet": check_symbol_fields_module.Property("~", True),
            "Description": check_symbol_fields_module.Property("10k resistor", True),
            "Manufacturer": check_symbol_fields_module.Property("Test", True),
            "Mfr. Part #": check_symbol_fields_module.Property("TEST-1", True),
            "LCSC ID": check_symbol_fields_module.Property("C1", True),
            "Package": check_symbol_fields_module.Property("0603", True),
        },
    )

    issues, warnings = check_symbol_fields_module.validate_symbol(symbol)

    assert issues == []
    assert warnings == []


def test_extended_passive_symbol_suppresses_warning(check_symbol_fields_module) -> None:
    symbol = check_symbol_fields_module.Symbol(
        name="R_Test_Extended",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        pin_count=0,
        extends="R_Base",
        properties={
            "Reference": check_symbol_fields_module.Property("R", False),
            "Value": check_symbol_fields_module.Property("100k", False),
            "Footprint": check_symbol_fields_module.Property(
                "GS_Resistors:R_0603_1608Metric",
                True,
            ),
            "Datasheet": check_symbol_fields_module.Property("~", True),
            "Description": check_symbol_fields_module.Property("100k resistor", True),
            "Manufacturer": check_symbol_fields_module.Property("Test", True),
            "Mfr. Part #": check_symbol_fields_module.Property("TEST-1", True),
            "LCSC ID": check_symbol_fields_module.Property("C1", True),
            "Package": check_symbol_fields_module.Property("0603", True),
        },
    )

    issues, warnings = check_symbol_fields_module.validate_symbol(symbol)

    assert issues == []
    assert warnings == []


def test_override_field_short_circuits_required_fields(check_symbol_fields_module) -> None:
    symbol = check_symbol_fields_module.Symbol(
        name="DraftPart",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        pin_count=3,
        extends=None,
        properties={
            "Reference": check_symbol_fields_module.Property("U", False),
            "Value": check_symbol_fields_module.Property("DraftPart", False),
            "Field Validation Override": check_symbol_fields_module.Property(
                "prototype symbol",
                True,
            ),
        },
    )

    issues, warnings = check_symbol_fields_module.validate_symbol(symbol)

    assert issues == []
    assert warnings == []
