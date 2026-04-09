from __future__ import annotations

import pytest

from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.importer import FootprintLinkChoice, describe_footprint_link


def test_generated_reference_uses_imported_footprint() -> None:
    choice = FootprintLinkChoice(mode="generated")
    assert (
        choice.reference(
            generated_library="GS_SO",
            generated_footprint="SOIC-8_5.3x5.3mm_P1.27mm",
        )
        == "GS_SO:SOIC-8_5.3x5.3mm_P1.27mm"
    )


def test_existing_reference_stays_wrapper_owned() -> None:
    choice = FootprintLinkChoice(
        mode="existing",
        existing_library="GS_SO",
        existing_footprint="SOIC-8_5.3x5.3mm_P1.27mm",
    )
    assert (
        choice.reference(generated_library=None, generated_footprint=None)
        == "GS_SO:SOIC-8_5.3x5.3mm_P1.27mm"
    )


def test_none_reference_returns_empty_string() -> None:
    assert FootprintLinkChoice(mode="none").reference(None, None) == ""


def test_generated_reference_requires_staged_footprint() -> None:
    with pytest.raises(ImportErrorWithExitCode):
        FootprintLinkChoice(mode="generated").reference(None, None)


def test_describe_existing_footprint_link() -> None:
    choice = FootprintLinkChoice(
        mode="existing",
        existing_library="GS_SO",
        existing_footprint="SOIC-8_5.3x5.3mm_P1.27mm",
    )
    assert describe_footprint_link(choice) == "existing GS_SO:SOIC-8_5.3x5.3mm_P1.27mm"
