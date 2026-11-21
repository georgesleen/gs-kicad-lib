from __future__ import annotations

from pathlib import Path

from kicad_lib_tools import validation


def test_missing_spice_configuration_is_warning_only() -> None:
    symbol = validation.Symbol(
        name="TestPart",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        exclude_from_sim=None,
        pin_count=3,
        extends=None,
        properties={
            "Reference": validation.Property("U", False),
            "Value": validation.Property("TestPart", False),
            "Footprint": validation.Property("GS_SO:SOT-23", True),
            "Datasheet": validation.Property("~", True),
            "Description": validation.Property("test part", True),
            "Manufacturer": validation.Property("Test", True),
            "MPN": validation.Property("TEST-1", True),
            "LCSC ID": validation.Property("C1", True),
            "Package": validation.Property("SOT-23", True),
        },
    )

    issues, warnings = validation.validate_symbol(symbol)

    assert issues == []
    assert warnings == ["no SPICE model configured"]


def test_spice_warning_override_suppresses_warning() -> None:
    symbol = validation.Symbol(
        name="TestPart",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        exclude_from_sim=None,
        pin_count=3,
        extends=None,
        properties={
            "Reference": validation.Property("U", False),
            "Value": validation.Property("TestPart", False),
            "Footprint": validation.Property("GS_SO:SOT-23", True),
            "Datasheet": validation.Property("~", True),
            "Description": validation.Property("test part", True),
            "Manufacturer": validation.Property("Test", True),
            "MPN": validation.Property("TEST-1", True),
            "LCSC ID": validation.Property("C1", True),
            "Package": validation.Property("SOT-23", True),
            "SPICE Warning Override": validation.Property(
                "digital-only symbol",
                True,
            ),
        },
    )

    issues, warnings = validation.validate_symbol(symbol)

    assert issues == []
    assert warnings == []


def test_inferred_passive_model_suppresses_warning() -> None:
    symbol = validation.Symbol(
        name="R_Test",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        exclude_from_sim=None,
        pin_count=2,
        extends=None,
        properties={
            "Reference": validation.Property("R", False),
            "Value": validation.Property("10k", False),
            "Footprint": validation.Property(
                "GS_Resistors:R_0603_1608Metric",
                True,
            ),
            "Datasheet": validation.Property("~", True),
            "Description": validation.Property("10k resistor", True),
            "Manufacturer": validation.Property("Test", True),
            "MPN": validation.Property("TEST-1", True),
            "LCSC ID": validation.Property("C1", True),
            "Package": validation.Property("0603", True),
        },
    )

    issues, warnings = validation.validate_symbol(symbol)

    assert issues == []
    assert warnings == []


def test_extended_passive_symbol_suppresses_warning() -> None:
    symbol = validation.Symbol(
        name="R_Test_Extended",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        exclude_from_sim=None,
        pin_count=0,
        extends="R_Base",
        properties={
            "Reference": validation.Property("R", False),
            "Value": validation.Property("100k", False),
            "Footprint": validation.Property(
                "GS_Resistors:R_0603_1608Metric",
                True,
            ),
            "Datasheet": validation.Property("~", True),
            "Description": validation.Property("100k resistor", True),
            "Manufacturer": validation.Property("Test", True),
            "MPN": validation.Property("TEST-1", True),
            "LCSC ID": validation.Property("C1", True),
            "Package": validation.Property("0603", True),
        },
    )

    issues, warnings = validation.validate_symbol(symbol)

    assert issues == []
    assert warnings == []


def test_override_field_short_circuits_required_fields() -> None:
    symbol = validation.Symbol(
        name="DraftPart",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        exclude_from_sim=None,
        pin_count=3,
        extends=None,
        properties={
            "Reference": validation.Property("U", False),
            "Value": validation.Property("DraftPart", False),
            "Field Validation Override": validation.Property(
                "prototype symbol",
                True,
            ),
        },
    )

    issues, warnings = validation.validate_symbol(symbol)

    assert issues == []
    assert warnings == []


def test_legacy_mfr_part_field_is_rejected() -> None:
    symbol = validation.Symbol(
        name="LegacyPart",
        path=Path("symbols/Test.kicad_sym"),
        in_bom=True,
        exclude_from_sim=None,
        pin_count=3,
        extends=None,
        properties={
            "Reference": validation.Property("U", False),
            "Value": validation.Property("LegacyPart", False),
            "Footprint": validation.Property("GS_SO:SOT-23", True),
            "Datasheet": validation.Property("~", True),
            "Description": validation.Property("test part", True),
            "Manufacturer": validation.Property("Test", True),
            "Mfr. Part #": validation.Property("TEST-1", True),
            "LCSC ID": validation.Property("C1", True),
            "Package": validation.Property("SOT-23", True),
        },
    )

    issues, warnings = validation.validate_symbol(symbol)

    assert issues == ['use "MPN" instead of "Mfr. Part #"']
    assert warnings == ["no SPICE model configured"]


def test_exclude_from_sim_suppresses_spice_warning() -> None:
    symbol = validation.Symbol(
        name="+3.3V",
        path=Path("symbols/GS_Power_Symbols.kicad_sym"),
        in_bom=False,
        exclude_from_sim=True,
        pin_count=1,
        extends=None,
        properties={
            "Reference": validation.Property("#PWR", True),
            "Value": validation.Property("+3.3V", False),
            "Footprint": validation.Property("", True),
            "Datasheet": validation.Property("", True),
            "Description": validation.Property(
                'Power symbol creates a local label with name "+3.3V"', True
            ),
        },
    )

    issues, warnings = validation.validate_symbol(symbol)

    assert issues == []
    assert warnings == []
