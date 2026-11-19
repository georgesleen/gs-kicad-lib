from __future__ import annotations

import pytest

from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.lcsc_api import parse_part


def test_parse_part_reads_fields_and_attributes() -> None:
    body = {
        "ok": True,
        "result": {
            "brandNameEn": "Infineon",
            "productModel": "BSS308PEH6327",
            "productDescEn": "P-Channel 30V 2A 0.5W Surface Mount SOT-23",
            "pdfUrl": "https://example.invalid/ds.pdf",
            "encapStandard": "SOT-23",
            "catalogName": "Single FETs, MOSFETs",
            "parentCatalogName": "Transistors/Thyristors",
            "paramVOList": [
                {"paramNameEn": "Drain to Source Voltage", "paramValueEn": "30V"},
                {"paramNameEn": "Configuration", "paramValueEn": ""},
            ],
        },
    }
    part = parse_part("C2939946", body)
    assert part.mpn == "BSS308PEH6327"
    assert part.parent_category == "Transistors/Thyristors"
    assert part.attributes == {"Drain to Source Voltage": "30V"}


def test_parse_part_turns_null_fields_into_empty_strings() -> None:
    part = parse_part("C2040", {"ok": True, "result": {"productDescEn": None}})
    assert part.description == ""
    assert part.manufacturer == ""
    assert part.attributes == {}


def test_parse_part_rejects_error_responses() -> None:
    with pytest.raises(ImportErrorWithExitCode, match="LCSC API error for C1: not found"):
        parse_part("C1", {"ok": False, "msg": "not found"})
