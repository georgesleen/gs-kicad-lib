from __future__ import annotations

import pytest

from kicad_lib_tools.families import (
    PartSuggestion,
    compact_units,
    condition_free,
    millivolts,
    name_package,
    suggest_for_part,
)
from kicad_lib_tools.lcsc_api import LCSCPart


def make_part(category: str, package: str, attributes: dict[str, str], mpn: str = "X") -> LCSCPart:
    return LCSCPart(
        lcsc_id="C1",
        manufacturer="",
        mpn=mpn,
        description="",
        datasheet_url="",
        package=package,
        category=category,
        parent_category="",
        attributes=attributes,
    )


def test_p_channel_mosfet_uses_negative_ratings() -> None:
    part = make_part(
        "Single FETs, MOSFETs",
        "SOT-23",
        {
            "Drain to Source Voltage": "20V",
            "Current - Continuous Drain(Id)": "4.8A",
            "RDS(on)": "37mΩ@4.5V",
            "Number": "1 P-Channel",
            "Gate Threshold Voltage (Vgs(th))": "400mV",
        },
        mpn="AO3415",
    )
    assert suggest_for_part(part) == PartSuggestion(
        name="MOSFET_P-Ch_-20V_4.8A_37mR_-400mVth",
        value="AO3415",
        description="P-Channel MOSFET, -20V Vds, -4.8A Id, 37mR Rds(on), -400mV Vth, SOT-23",
    )


def test_n_channel_mosfet_keeps_positive_ratings() -> None:
    part = make_part(
        "Single FETs, MOSFETs",
        "TO-220AB",
        {
            "Drain to Source Voltage": "55V",
            "Current - Continuous Drain(Id)": "49A",
            "RDS(on)": "17.5mΩ@10V",
            "Type": "N-Channel",
            "Gate Threshold Voltage (Vgs(th))": "4V",
        },
    )
    suggestion = suggest_for_part(part)
    assert suggestion is not None
    assert suggestion.name == "MOSFET_N-Ch_55V_49A_17.5mR_4Vth"


@pytest.mark.parametrize(
    ("forward", "name"),
    [("580mV@1A", "D_Schottky_580mV_1A"), ("1.1V@1A", "D_Rectifier_1.1V_1A")],
)
def test_diode_kind_follows_forward_voltage(forward: str, name: str) -> None:
    part = make_part(
        "Single Diodes",
        "SOD-123",
        {
            "Voltage - Forward(Vf@If)": forward,
            "Current - Rectified": "1A",
            "Voltage - DC Reverse (Vr) (Max)": "40V",
        },
    )
    suggestion = suggest_for_part(part)
    assert suggestion is not None
    assert suggestion.name == name
    assert suggestion.description.endswith("Vf at 1A, SOD-123")


def test_zener_uses_nominal_voltage_and_power() -> None:
    part = make_part(
        "Single Zener Diodes",
        "0603(SOD-523F)",
        {"Zener Voltage(Nom)": "6.2V", "Pd - Power Dissipation": "150mW"},
    )
    assert suggest_for_part(part) == PartSuggestion(
        name="D_Zener_6.2V_150mW",
        value="6.2V",
        description="Zener diode, 6.2V, 150mW, 0603(SOD-523F)",
    )


def test_inductor_names_package_without_smd_prefix() -> None:
    part = make_part(
        "Fixed Inductors",
        "SMD,12x12mm",
        {
            "Current Rating": "4A",
            "Inductance": "27uH",
            "Tolerance": "±20%",
            "DC Resistance(DCR)": "46mΩ",
            "Current - Saturation(Isat)": "4A",
        },
    )
    assert suggest_for_part(part) == PartSuggestion(
        name="L_12x12mm_27uH",
        value="27uH",
        description="Inductor, 27uH 20%, 4A rated, 4A saturation, 46mR DCR, SMD,12x12mm",
    )


def test_ferrite_bead_splits_impedance_and_frequency() -> None:
    part = make_part(
        "Ferrite Beads and Chips",
        "0805",
        {
            "DC Resistance(DCR)": "40mΩ",
            "Current Rating": "3A",
            "Impedance @ Frequency": "120Ω@100MHz",
        },
    )
    assert suggest_for_part(part) == PartSuggestion(
        name="FB_0805_120R",
        value="120R @ 100MHz",
        description="Ferrite bead, 120R at 100MHz, 3A, 40mR DCR, 0805",
    )


def test_led_takes_the_base_colour() -> None:
    part = make_part(
        "LED Indication - Discrete",
        "0402",
        {
            "Peak Wavelength": "531nm",
            "Forward Current": "25mA",
            "Illumination Color": "Emerald Green",
            "Voltage - Forward(Vf)": "3V",
        },
    )
    assert suggest_for_part(part) == PartSuggestion(
        name="LED_0402_Green",
        value="Green",
        description="Green LED, 531nm, 3V Vf, 25mA, 0402",
    )


def test_crystal_strips_smd_and_pin_count_from_package() -> None:
    part = make_part(
        "Crystals",
        "SMD3225-4P",
        {
            "Normal temperature Frequency Tolerance": "±10ppm",
            "Frequency Stability": "±50ppm",
            "Load Capacitance": "12pF",
            "Frequency": "12MHz",
        },
    )
    assert suggest_for_part(part) == PartSuggestion(
        name="Crystal_3225_12MHz",
        value="12MHz 12pF",
        description=("Crystal, 12MHz, 12pF load, ±10ppm tolerance, ±50ppm stability, SMD3225-4P"),
    )


def test_missing_or_dash_attributes_give_no_suggestion() -> None:
    part = make_part("Single Zener Diodes", "SOD-123", {"Zener Voltage(Nom)": "-"})
    assert suggest_for_part(part) is None
    assert suggest_for_part(make_part("Microcontrollers", "QFN-56", {})) is None


def test_unit_helpers() -> None:
    assert condition_free("37mΩ@4.5V") == "37mΩ"
    assert compact_units("±20 %") == "20%"
    assert millivolts("580mV") == 580.0
    assert millivolts("1.1V") == 1100.0
    assert millivolts("n/a") is None
    assert name_package("SMD,2.7x3mm") == "2.7x3mm"
