"""Symbol name, value, and description templates for common part families."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from .config import ConfigError, FamilyFormat, get_config
from .lcsc_api import LCSCPart

SCHOTTKY_MAX_FORWARD_MV = 600.0


@dataclass(frozen=True)
class PartSuggestion:
    """Suggested symbol name, Value, Description, and Reference fields for a part.

    An empty ``reference`` keeps the reference designator of the source symbol.
    """

    name: str
    value: str
    description: str
    reference: str = ""


class UnsupportedPart(Exception):
    """A part that its category's family template does not cover."""


class MissingAttribute(UnsupportedPart):
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


Variables = dict[str, str]


def mosfet(part: LCSCPart) -> Variables:
    p_channel = "P-CHANNEL" in attribute(part, "Type", "Number").upper()

    def sign(value: str) -> str:
        return negated(value) if p_channel else value

    current = attribute(part, "Current - Continuous Drain(Id)")
    return {
        "polarity": "P" if p_channel else "N",
        "vds": sign(attribute(part, "Drain to Source Voltage")),
        "current": current,
        "id": sign(current),
        "rds": compact_units(condition_free(attribute(part, "RDS(on)"))),
        "vth": sign(condition_free(attribute(part, "Gate Threshold Voltage (Vgs(th))"))),
    }


def diode(part: LCSCPart) -> Variables:
    forward_full = attribute(part, "Voltage - Forward(Vf@If)")
    forward = condition_free(forward_full)
    forward_mv = millivolts(forward)
    schottky = forward_mv is not None and forward_mv <= SCHOTTKY_MAX_FORWARD_MV
    at_current = forward_full.split("@", 1)[1] if "@" in forward_full else ""
    return {
        "kind": "Schottky" if schottky else "Rectifier",
        "forward": forward,
        "at_current": f"at {at_current}" if at_current else "",
        "current": attribute(part, "Current - Rectified"),
        "reverse": attribute(part, "Voltage - DC Reverse (Vr) (Max)"),
    }


def zener(part: LCSCPart) -> Variables:
    return {
        "voltage": attribute(part, "Zener Voltage(Nom)"),
        "power": attribute(part, "Pd - Power Dissipation"),
    }


def inductor(part: LCSCPart) -> Variables:
    return {
        "inductance": attribute(part, "Inductance"),
        "tolerance": compact_units(attribute(part, "Tolerance")),
        "rated": attribute(part, "Current Rating"),
        "saturation": attribute(part, "Current - Saturation(Isat)"),
        "dcr": compact_units(attribute(part, "DC Resistance(DCR)")),
    }


def ferrite_bead(part: LCSCPart) -> Variables:
    impedance_full = compact_units(attribute(part, "Impedance @ Frequency"))
    impedance, _, frequency = impedance_full.partition("@")
    return {
        "impedance": impedance,
        "frequency": frequency,
        "impedance_at": f"{impedance} at {frequency}" if frequency else impedance,
        "impedance_value": f"{impedance} @ {frequency}" if frequency else impedance,
        "rated": attribute(part, "Current Rating"),
        "dcr": compact_units(attribute(part, "DC Resistance(DCR)")),
    }


def indicator_led(part: LCSCPart) -> Variables:
    return {
        "colour": attribute(part, "Illumination Color").split()[-1].capitalize(),
        "wavelength": attribute(part, "Peak Wavelength", "Wavelength - Dominant"),
        "forward": attribute(part, "Voltage - Forward(Vf)"),
        "current": attribute(part, "Forward Current", "Current - DC Forward(If)"),
    }


def crystal(part: LCSCPart) -> Variables:
    return {
        "crystal_package": re.sub(r"^SMD", "", name_package(part.package)),
        "frequency": attribute(part, "Frequency"),
        "load": attribute(part, "Load Capacitance"),
        "tolerance": attribute(part, "Normal temperature Frequency Tolerance"),
        "stability": attribute(part, "Frequency Stability"),
    }


USB_C_CAPABILITIES: dict[int, tuple[str, str]] = {
    2: ("PowerOnly", "power only"),
    6: ("PowerOnly", "power only"),
    12: ("USB2", "USB 2.0"),
    14: ("USB2", "USB 2.0"),
    16: ("USB2", "USB 2.0"),
    24: ("SS", "USB 3.2"),
}

MOUNTING_TERMS = {"surface mount": "SMD", "through hole": "THT"}


def mounting(value: str) -> str:
    """Return an LCSC mounting type in repo notation, ``Surface Mount`` becoming ``SMD``."""
    terms = (term.strip() for term in value.split(","))
    return " ".join(MOUNTING_TERMS.get(term.lower(), term.lower()) for term in terms if term)


def usb_c_socket(part: LCSCPart) -> Variables:
    if attribute(part, "Connector Type") != "Type-C" or attribute(part, "Gender") != "Female":
        raise UnsupportedPart(part.lcsc_id)
    match = re.fullmatch(r"(\d+)P", attribute(part, "Number of Contacts"))
    contacts = int(match.group(1)) if match else 0
    if contacts not in USB_C_CAPABILITIES:
        raise UnsupportedPart(part.lcsc_id)
    capability_short, capability = USB_C_CAPABILITIES[contacts]
    return {
        "capability_short": capability_short,
        "capability": capability,
        "contacts": str(contacts),
        "mounting": mounting(part.attributes.get("Mounting Type", "")),
    }


@dataclass(frozen=True)
class Family:
    """A part family: the variables it reads from LCSC and its default field formats."""

    variables: Callable[[LCSCPart], Variables]
    format: FamilyFormat


FAMILIES: dict[str, Family] = {
    "mosfet": Family(
        mosfet,
        FamilyFormat(
            name="MOSFET_{polarity}-Ch_{vds}_{current}_{rds}_{vth}th",
            value="{mpn}",
            description=(
                "{polarity}-Channel MOSFET",
                "{vds} Vds",
                "{id} Id",
                "{rds} Rds(on)",
                "{vth} Vth",
                "{package}",
            ),
        ),
    ),
    "diode": Family(
        diode,
        FamilyFormat(
            name="D_{kind}_{forward}_{current}",
            value="{forward} {current}",
            description=(
                "{kind} diode",
                "{reverse} Vr",
                "{current} If",
                "{forward} Vf {at_current}",
                "{package}",
            ),
        ),
    ),
    "zener": Family(
        zener,
        FamilyFormat(
            name="D_Zener_{voltage}_{power}",
            value="{voltage}",
            description=("Zener diode", "{voltage}", "{power}", "{package}"),
        ),
    ),
    "inductor": Family(
        inductor,
        FamilyFormat(
            name="L_{name_package}_{inductance}",
            value="{inductance}",
            description=(
                "Inductor",
                "{inductance} {tolerance}",
                "{rated} rated",
                "{saturation} saturation",
                "{dcr} DCR",
                "{package}",
            ),
        ),
    ),
    "ferrite_bead": Family(
        ferrite_bead,
        FamilyFormat(
            name="FB_{name_package}_{impedance}",
            value="{impedance_value}",
            description=("Ferrite bead", "{impedance_at}", "{rated}", "{dcr} DCR", "{package}"),
        ),
    ),
    "indicator_led": Family(
        indicator_led,
        FamilyFormat(
            name="LED_{name_package}_{colour}",
            value="{colour}",
            description=(
                "{colour} LED",
                "{wavelength}",
                "{forward} Vf",
                "{current}",
                "{package}",
            ),
        ),
    ),
    "crystal": Family(
        crystal,
        FamilyFormat(
            name="Crystal_{crystal_package}_{frequency}",
            value="{frequency} {load}",
            description=(
                "Crystal",
                "{frequency}",
                "{load} load",
                "{tolerance} tolerance",
                "{stability} stability",
                "{package}",
            ),
        ),
    ),
    "usb_c_socket": Family(
        usb_c_socket,
        FamilyFormat(
            name="USB_C_Socket_{capability_short}",
            value="USB_C_Socket_{capability_short}",
            description=(
                "USB Type-C receptacle",
                "{capability}",
                "{contacts} contacts",
                "{mounting}",
            ),
            reference="J",
        ),
    ),
}

CATEGORY_FAMILIES: dict[str, str] = {
    "Single FETs, MOSFETs": "mosfet",
    "Single Diodes": "diode",
    "Single Zener Diodes": "zener",
    "Fixed Inductors": "inductor",
    "Ferrite Beads and Chips": "ferrite_bead",
    "LED Indication - Discrete": "indicator_led",
    "Crystals": "crystal",
    "USB, DVI, HDMI Connector Assemblies": "usb_c_socket",
}


def family_format(family: str) -> FamilyFormat:
    """Return the default format of ``family`` with the overrides from the config.

    Raises:
        ConfigError: if the config overrides a family that does not exist.
    """
    overrides = get_config().family_formats
    unknown = sorted(set(overrides) - set(FAMILIES))
    if unknown:
        raise ConfigError(f"kicad-lib.toml: unknown part families: {', '.join(unknown)}")
    return replace(FAMILIES[family].format, **overrides.get(family, {}))


def render(family: str, template: str, variables: Variables) -> str:
    """Return ``template`` with the family's variables filled in.

    Raises:
        ConfigError: if the template names a variable that the family does not have.
    """
    try:
        return template.format(**variables).strip()
    except KeyError as err:
        raise ConfigError(
            f"kicad-lib.toml: part family {family} has no variable {err}; "
            f"it has {', '.join(sorted(variables))}"
        ) from err


def part_variables(part: LCSCPart) -> Variables:
    """Return the variables that every part family has."""
    return {
        "mpn": part.mpn,
        "manufacturer": part.manufacturer,
        "lcsc_id": part.lcsc_id,
        "package": part.package,
        "name_package": name_package(part.package),
    }


def suggest_for_part(part: LCSCPart) -> PartSuggestion | None:
    """Return the family suggestion for a part, or None if no family template fits its data.

    Raises:
        ConfigError: if a configured family format is invalid.
    """
    family = CATEGORY_FAMILIES.get(part.category)
    if family is None:
        return None
    try:
        variables = part_variables(part) | FAMILIES[family].variables(part)
    except UnsupportedPart:
        return None
    fmt = family_format(family)
    parts = (render(family, template, variables) for template in fmt.description)
    return PartSuggestion(
        name=render(family, fmt.name, variables),
        value=render(family, fmt.value, variables),
        description=", ".join(part for part in parts if part),
        reference=render(family, fmt.reference, variables),
    )
