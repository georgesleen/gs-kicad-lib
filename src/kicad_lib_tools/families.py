"""Symbol name, value, and description templates for common part families."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .lcsc_api import LCSCPart

SCHOTTKY_MAX_FORWARD_MV = 600.0


@dataclass(frozen=True)
class PartSuggestion:
    """Suggested symbol name, Value field, and Description field for a part."""

    name: str
    value: str
    description: str


class MissingAttribute(Exception):
    """An LCSC attribute that a family template needs is absent or blank."""


def attribute(part: LCSCPart, *names: str) -> str:
    """Return the first of ``names`` that the part has with a real value.

    Raises:
        MissingAttribute: if none of the attributes has a value.
    """
    for name in names:
        value = part.attributes.get(name, "").strip()
        if value and value != "-":
            return value
    raise MissingAttribute(names[0])


def condition_free(value: str) -> str:
    """Return a value without its test condition, ``580mV@1A`` becoming ``580mV``."""
    return value.split("@", 1)[0].strip()


def compact_units(value: str) -> str:
    """Return a value in repo notation: ohms as ``R``, no plus-minus sign, no spaces."""
    return value.replace("Ω", "R").replace("±", "").replace(" ", "")


def negated(value: str) -> str:
    """Return a value with a leading minus sign, keeping an existing one."""
    return value if value.startswith("-") else f"-{value}"


def millivolts(value: str) -> float | None:
    """Return a voltage such as ``580mV`` or ``1.1V`` in millivolts, or None if unparsable."""
    match = re.fullmatch(r"([\d.]+)\s*(m?)V", value.strip())
    if not match:
        return None
    return float(match.group(1)) * (1.0 if match.group(2) else 1000.0)


def name_package(package: str) -> str:
    """Return the package part of a symbol name, ``SMD,12x12mm`` becoming ``12x12mm``."""
    value = re.sub(r"^SMD[,\s]*", "", package.strip())
    value = re.sub(r"-\d+P$", "", value)
    return value.replace(",", "_").replace(" ", "")


def join(*fields: str) -> str:
    """Return the non-empty fields joined with commas."""
    return ", ".join(field for field in fields if field)


def mosfet(part: LCSCPart) -> PartSuggestion:
    p_channel = "P-CHANNEL" in attribute(part, "Type", "Number").upper()

    def sign(value: str) -> str:
        return negated(value) if p_channel else value

    vds = sign(attribute(part, "Drain to Source Voltage"))
    current = attribute(part, "Current - Continuous Drain(Id)")
    rds = compact_units(condition_free(attribute(part, "RDS(on)")))
    vth = sign(condition_free(attribute(part, "Gate Threshold Voltage (Vgs(th))")))
    polarity = "P" if p_channel else "N"
    return PartSuggestion(
        name=f"MOSFET_{polarity}-Ch_{vds}_{current}_{rds}_{vth}th",
        value=part.mpn,
        description=join(
            f"{polarity}-Channel MOSFET",
            f"{vds} Vds",
            f"{sign(current)} Id",
            f"{rds} Rds(on)",
            f"{vth} Vth",
            part.package,
        ),
    )


def diode(part: LCSCPart) -> PartSuggestion:
    forward_full = attribute(part, "Voltage - Forward(Vf@If)")
    forward = condition_free(forward_full)
    current = attribute(part, "Current - Rectified")
    reverse = attribute(part, "Voltage - DC Reverse (Vr) (Max)")
    forward_mv = millivolts(forward)
    schottky = forward_mv is not None and forward_mv <= SCHOTTKY_MAX_FORWARD_MV
    kind = "Schottky" if schottky else "Rectifier"
    at_current = forward_full.split("@", 1)[1] if "@" in forward_full else ""
    return PartSuggestion(
        name=f"D_{kind}_{forward}_{current}",
        value=f"{forward} {current}",
        description=join(
            f"{kind} diode",
            f"{reverse} Vr",
            f"{current} If",
            f"{forward} Vf" + (f" at {at_current}" if at_current else ""),
            part.package,
        ),
    )


def zener(part: LCSCPart) -> PartSuggestion:
    voltage = attribute(part, "Zener Voltage(Nom)")
    power = attribute(part, "Pd - Power Dissipation")
    return PartSuggestion(
        name=f"D_Zener_{voltage}_{power}",
        value=voltage,
        description=join("Zener diode", voltage, power, part.package),
    )


def inductor(part: LCSCPart) -> PartSuggestion:
    inductance = attribute(part, "Inductance")
    tolerance = compact_units(attribute(part, "Tolerance"))
    rated = attribute(part, "Current Rating")
    saturation = attribute(part, "Current - Saturation(Isat)")
    dcr = compact_units(attribute(part, "DC Resistance(DCR)"))
    return PartSuggestion(
        name=f"L_{name_package(part.package)}_{inductance}",
        value=inductance,
        description=join(
            "Inductor",
            f"{inductance} {tolerance}",
            f"{rated} rated",
            f"{saturation} saturation",
            f"{dcr} DCR",
            part.package,
        ),
    )


def ferrite_bead(part: LCSCPart) -> PartSuggestion:
    impedance_full = compact_units(attribute(part, "Impedance @ Frequency"))
    impedance, _, frequency = impedance_full.partition("@")
    rated = attribute(part, "Current Rating")
    dcr = compact_units(attribute(part, "DC Resistance(DCR)"))
    return PartSuggestion(
        name=f"FB_{name_package(part.package)}_{impedance}",
        value=f"{impedance} @ {frequency}" if frequency else impedance,
        description=join(
            "Ferrite bead",
            f"{impedance} at {frequency}" if frequency else impedance,
            rated,
            f"{dcr} DCR",
            part.package,
        ),
    )


def indicator_led(part: LCSCPart) -> PartSuggestion:
    colour = attribute(part, "Illumination Color").split()[-1].capitalize()
    wavelength = attribute(part, "Peak Wavelength", "Wavelength - Dominant")
    forward = attribute(part, "Voltage - Forward(Vf)")
    current = attribute(part, "Forward Current", "Current - DC Forward(If)")
    return PartSuggestion(
        name=f"LED_{name_package(part.package)}_{colour}",
        value=colour,
        description=join(f"{colour} LED", wavelength, f"{forward} Vf", current, part.package),
    )


def crystal(part: LCSCPart) -> PartSuggestion:
    frequency = attribute(part, "Frequency")
    load = attribute(part, "Load Capacitance")
    tolerance = attribute(part, "Normal temperature Frequency Tolerance")
    stability = attribute(part, "Frequency Stability")
    package = re.sub(r"^SMD", "", name_package(part.package))
    return PartSuggestion(
        name=f"Crystal_{package}_{frequency}",
        value=f"{frequency} {load}",
        description=join(
            "Crystal",
            frequency,
            f"{load} load",
            f"{tolerance} tolerance",
            f"{stability} stability",
            part.package,
        ),
    )


FAMILIES: dict[str, Callable[[LCSCPart], PartSuggestion]] = {
    "Single FETs, MOSFETs": mosfet,
    "Single Diodes": diode,
    "Single Zener Diodes": zener,
    "Fixed Inductors": inductor,
    "Ferrite Beads and Chips": ferrite_bead,
    "LED Indication - Discrete": indicator_led,
    "Crystals": crystal,
}


def suggest_for_part(part: LCSCPart) -> PartSuggestion | None:
    """Return the family suggestion for a part, or None if no template fits its data."""
    template = FAMILIES.get(part.category)
    if template is None:
        return None
    try:
        return template(part)
    except MissingAttribute:
        return None
