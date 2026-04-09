from __future__ import annotations

from kicad_lib_tools.symbols import parse_symbol_properties, prepare_symbol_block


def test_prepare_symbol_block_rewrites_converter_symbol_to_repo_field_schema() -> None:
    symbol_text = """\
(symbol "TPS5430DDAR"
  (property "Reference" "U" (id 0) (at 0 7.62 0) (effects (font (size 1.27 1.27))))
  (property "Value" "TPS5430DDAR" (id 1) (at 0 0 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "easyeda2kicad:SOIC-8_5.3x5.3mm_P1.27mm" (id 2) (at 0 -2.54 0) (effects (font (size 1.27 1.27)) hide))
  (property "Datasheet" "https://www.lcsc.com/datasheet/C3235552.pdf" (id 3) (at 0 -5.08 0) (effects (font (size 1.27 1.27)) hide))
  (property "LCSC Part" "C3235552" (id 6) (at 0 -7.62 0) (effects (font (size 1.27 1.27)) hide))
)
"""

    updated = prepare_symbol_block(
        symbol_block=symbol_text,
        footprint_ref="GS_SO:SOIC-8_5.3x5.3mm_P1.27mm",
        datasheet="https://www.lcsc.com/datasheet/C3235552.pdf",
        description="Buck regulator",
        manufacturer="Texas Instruments",
        mpn="TPS5430DDAR",
        lcsc_id="C3235552",
        package="SOIC-8_5.3x5.3mm_P1.27mm",
        validation_override="",
        spice_warning_override="",
    )

    properties = {prop.name: prop for prop in parse_symbol_properties(updated)}

    assert "LCSC Part" not in properties
    assert "Mfr. Part #" not in properties
    assert properties["Footprint"].value == "GS_SO:SOIC-8_5.3x5.3mm_P1.27mm"
    assert properties["Manufacturer"].value == "Texas Instruments"
    assert properties["MPN"].value == "TPS5430DDAR"
    assert properties["LCSC ID"].value == "C3235552"
    assert properties["Package"].value == "SOIC-8_5.3x5.3mm_P1.27mm"


def test_prepare_symbol_block_removes_empty_validation_override() -> None:
    symbol_text = """\
(symbol "TPS5430DDAR"
  (property "Reference" "U" (id 0) (at 0 7.62 0) (effects (font (size 1.27 1.27))))
  (property "Value" "TPS5430DDAR" (id 1) (at 0 0 0) (effects (font (size 1.27 1.27))))
  (property "Field Validation Override" "legacy" (id 7) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
)
"""
    updated = prepare_symbol_block(
        symbol_block=symbol_text,
        footprint_ref="",
        datasheet="",
        description="Buck regulator",
        manufacturer="Texas Instruments",
        mpn="TPS5430DDAR",
        lcsc_id="C3235552",
        package="SOIC-8",
        validation_override="",
        spice_warning_override="",
    )
    properties = {prop.name: prop for prop in parse_symbol_properties(updated)}
    assert "Field Validation Override" not in properties
    assert "SPICE Warning Override" not in properties


def test_prepare_symbol_block_sets_spice_warning_override() -> None:
    symbol_text = """\
(symbol "TPS5430DDAR"
  (property "Reference" "U" (id 0) (at 0 7.62 0) (effects (font (size 1.27 1.27))))
  (property "Value" "TPS5430DDAR" (id 1) (at 0 0 0) (effects (font (size 1.27 1.27))))
)
"""
    updated = prepare_symbol_block(
        symbol_block=symbol_text,
        footprint_ref="",
        datasheet="",
        description="Buck regulator",
        manufacturer="Texas Instruments",
        mpn="TPS5430DDAR",
        lcsc_id="C3235552",
        package="SOIC-8",
        validation_override="",
        spice_warning_override="digital-only symbol",
    )
    properties = {prop.name: prop for prop in parse_symbol_properties(updated)}
    assert properties["SPICE Warning Override"].value == "digital-only symbol"
