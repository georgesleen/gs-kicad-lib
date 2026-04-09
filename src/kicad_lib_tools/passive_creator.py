"""Create derived passive symbols from LCSC part data."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import PassiveTypeConfig, get_config
from .errors import ImportErrorWithExitCode
from .interaction import prompt_text, prompt_yes_no
from .lcsc_api import LCSCPart, fetch_part
from .paths import SYMBOL_DIR, escape_kicad_string
from .selectors import SelectionOption, select_one
from .symbols import (
    SymbolBlock,
    parse_symbol_properties,
    parse_top_level_symbols,
    render_symbol_library_update,
    validate_symbol_library_text,
)


# ---------------------------------------------------------------------------
# Config-based passive type helpers
# ---------------------------------------------------------------------------


def _passive_types() -> dict[str, PassiveTypeConfig]:
    return get_config().passive_types  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------


def normalize_resistance(raw: str) -> str:
    """'5.1kΩ' → '5.1k', '100Ω' → '100R'."""
    value = raw.strip().rstrip("Ω\u2126")  # U+03A9 Ω and U+2126 Ω
    if value and value[-1].isdigit():
        value += "R"
    return value


def normalize_capacitance(raw: str) -> str:
    """'100nF' → '100nF', '10µF' → '10uF'."""
    return raw.strip().replace("µ", "u")


def normalize_value(raw: str, parent_category: str) -> str:
    if parent_category == "Resistors":
        return normalize_resistance(raw)
    if parent_category == "Capacitors":
        return normalize_capacitance(raw)
    return raw.strip()


# ---------------------------------------------------------------------------
# Description builders
# ---------------------------------------------------------------------------


def _strip_tolerance(raw: str) -> str:
    return raw.replace("±", "").strip()


def build_description(part: LCSCPart, value: str) -> str:
    attrs = part.attributes
    if part.parent_category == "Resistors":
        return _build_resistor_description(attrs, value)
    if part.parent_category == "Capacitors":
        return _build_capacitor_description(attrs, value)
    return part.description


def _build_resistor_description(attrs: dict[str, str], value: str) -> str:
    tolerance = _strip_tolerance(attrs.get("Tolerance", ""))
    power = (
        attrs.get("Power")
        or attrs.get("Power(Watts)")
        or attrs.get("Power Rating", "")
    )
    voltage = attrs.get("Voltage Rating", "")
    tempco_raw = attrs.get("Temperature Coefficient", "")
    tempco_match = re.search(r"(\d+)\s*ppm", tempco_raw)
    tempco = tempco_match.group(1) if tempco_match else ""

    parts = [f"{value} {tolerance} Resistor".rstrip()]
    if power:
        parts.append(f"{power} Max Power")
    if voltage:
        parts.append(f"{voltage} Max Voltage")
    if tempco:
        parts.append(f"{tempco}ppm")
    return ", ".join(parts)


def _build_capacitor_description(attrs: dict[str, str], value: str) -> str:
    tolerance = _strip_tolerance(attrs.get("Tolerance", ""))
    voltage = attrs.get("Voltage Rating", "")
    dielectric = attrs.get("Temperature Coefficient", "")

    parts = [f"{value} {tolerance} Unpolarized Capacitor".rstrip()]
    if voltage:
        parts.append(f"{voltage} Max Voltage")
    if dielectric:
        parts.append(dielectric)
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Library / symbol helpers
# ---------------------------------------------------------------------------


def determine_library_name(parent_category: str, package: str) -> str:
    passive_types = _passive_types()
    type_info = passive_types.get(parent_category)
    if not type_info:
        raise ImportErrorWithExitCode(
            f"unsupported passive category: {parent_category}", exit_code=1
        )
    return type_info.library_name_template.format(package=package)


def build_symbol_name(parent_category: str, package: str, value: str) -> str:
    passive_types = _passive_types()
    prefix = passive_types[parent_category].prefix
    return f"{prefix}_{package}_{value}"


def find_base_symbol(library_path: Path) -> SymbolBlock:
    """Return the first non-extended symbol in *library_path*."""
    text = library_path.read_text(encoding="utf-8")
    symbols = parse_top_level_symbols(text)
    for symbol in symbols:
        if "(extends " not in symbol.text:
            return symbol
    raise ImportErrorWithExitCode(
        f"no base symbol found in {library_path.name}", exit_code=1
    )


# ---------------------------------------------------------------------------
# Interactive field prompt (show default, let user override)
# ---------------------------------------------------------------------------


def prompt_field(label: str, default: str, *, required: bool = True) -> str:
    """Prompt for a field value, showing the pre-populated default.

    Press Enter to accept the default, or type a new value.
    """
    skip_hint = " (leave blank to skip)" if not required and not default else ""
    suffix = f" [{default}]" if default else ""
    while True:
        response = prompt_text(f"{label}{skip_hint}{suffix}: ").strip()
        if response:
            return response
        if default:
            return default
        if not required:
            return ""
        print(f"{label} is required.")


# ---------------------------------------------------------------------------
# Derived-symbol builder
# ---------------------------------------------------------------------------


def build_derived_symbol_block(
    base_symbol: SymbolBlock,
    new_name: str,
    overrides: dict[str, str],
) -> str:
    """Build a KiCad derived-symbol block that ``extends`` *base_symbol*.

    Property blocks are cloned from the base with values replaced according
    to *overrides*.
    """
    base_properties = parse_symbol_properties(base_symbol.text)
    base_lines = base_symbol.text.splitlines(keepends=True)

    parts: list[str] = []
    parts.append(f'\t(symbol "{escape_kicad_string(new_name)}"\n')
    parts.append(
        f'\t\t(extends "{escape_kicad_string(base_symbol.name)}")\n'
    )

    for prop in base_properties:
        prop_text = "".join(base_lines[prop.start : prop.end])
        if prop.name in overrides:
            new_value = escape_kicad_string(overrides[prop.name])
            prop_text = re.sub(
                r'(\(property\s+"[^"]*"\s+)"(?:[^"\\]|\\.)*"',
                rf'\1"{new_value}"',
                prop_text,
                count=1,
            )
        parts.append(prop_text)

    parts.append("\t\t(embedded_fonts no)\n")
    parts.append("\t)\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Plan dataclass
# ---------------------------------------------------------------------------


@dataclass
class PassivePlan:
    lcsc_id: str
    part: LCSCPart
    value: str
    symbol_name: str
    library_name: str
    library_path: Path
    base_symbol: SymbolBlock
    description: str
    datasheet: str
    manufacturer: str
    mpn: str
    package: str
    spice_warning_override: str


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------


def build_passive_plan(
    lcsc_id: str,
    interactive: bool,
) -> PassivePlan:
    print(f"Fetching {lcsc_id} from LCSC...")
    part = fetch_part(lcsc_id)

    passive_types = _passive_types()
    if part.parent_category not in passive_types:
        raise ImportErrorWithExitCode(
            f"{lcsc_id} is not a supported passive type "
            f"(category: {part.parent_category!r})",
            exit_code=1,
        )

    type_info = passive_types[part.parent_category]

    # --- value ---
    raw_value = part.attributes.get(type_info.value_param, "")
    if not raw_value and interactive:
        raw_value = prompt_text(
            "Value not detected. Enter value (e.g. 10k, 100nF): "
        )
    if not raw_value:
        raise ImportErrorWithExitCode(
            "could not determine component value from LCSC data", exit_code=1
        )
    value = normalize_value(raw_value, part.parent_category)

    # --- library ---
    library_name = determine_library_name(part.parent_category, part.package)
    library_path = SYMBOL_DIR / f"{library_name}.kicad_sym"

    if not library_path.exists() and interactive:
        existing = sorted(p.stem for p in SYMBOL_DIR.glob("*.kicad_sym"))
        options = [SelectionOption(lib, lib) for lib in existing]
        selected = select_one(
            title=(
                f"Library {library_name} does not exist "
                "— select target library"
            ),
            options=options,
        )
        library_name = selected.value
        library_path = SYMBOL_DIR / f"{library_name}.kicad_sym"

    if not library_path.exists():
        raise ImportErrorWithExitCode(
            f"library {library_name} does not exist — create it with "
            "'kicad-lib import' to establish a base symbol first",
            exit_code=1,
        )

    base_symbol = find_base_symbol(library_path)
    symbol_name = build_symbol_name(
        part.parent_category, part.package, value
    )
    description = build_description(part, value)
    mpn = part.mpn.replace("/", "_")

    # --- interactive field editing ---
    if interactive:
        print()
        print(f"  Library: {library_name}")
        print(f"  Base:    {base_symbol.name}")
        print()
        value = prompt_field("Value", value)
        # Rebuild symbol name and description if value changed
        symbol_name = build_symbol_name(
            part.parent_category, part.package, value
        )
        description = build_description(part, value)
        symbol_name = prompt_field("Symbol name", symbol_name)
        manufacturer = prompt_field("Manufacturer", part.manufacturer)
        mpn = prompt_field("MPN", mpn)
        datasheet = prompt_field("Datasheet", part.datasheet_url, required=False)
        description = prompt_field("Description", description)
        package = prompt_field("Package", part.package)
        spice_warning_override = prompt_field(
            "SPICE Warning Override", "", required=False
        )
    else:
        manufacturer = part.manufacturer
        datasheet = part.datasheet_url
        package = part.package
        spice_warning_override = ""

    return PassivePlan(
        lcsc_id=lcsc_id,
        part=part,
        value=value,
        symbol_name=symbol_name,
        library_name=library_name,
        library_path=library_path,
        base_symbol=base_symbol,
        description=description,
        datasheet=datasheet,
        manufacturer=manufacturer,
        mpn=mpn,
        package=package,
        spice_warning_override=spice_warning_override,
    )


# ---------------------------------------------------------------------------
# Apply plan
# ---------------------------------------------------------------------------


def apply_passive_plan(plan: PassivePlan, *, overwrite: bool = False) -> None:
    overrides: dict[str, str] = {
        "Value": plan.value,
        "Datasheet": plan.datasheet or "~",
        "Description": plan.description,
        "Manufacturer": plan.manufacturer,
        "MPN": plan.mpn,
        "LCSC ID": plan.lcsc_id,
        "Package": plan.package,
    }
    if plan.spice_warning_override:
        overrides["SPICE Warning Override"] = plan.spice_warning_override

    derived_block = build_derived_symbol_block(
        base_symbol=plan.base_symbol,
        new_name=plan.symbol_name,
        overrides=overrides,
    )
    rendered = render_symbol_library_update(
        symbol_library_path=plan.library_path,
        symbol_name=plan.symbol_name,
        symbol_block=derived_block,
        overwrite=overwrite,
    )
    validate_symbol_library_text(
        symbol_target=plan.library_path,
        content=rendered,
        verbose=False,
    )
    plan.library_path.write_text(rendered, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_passive_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add a derived passive symbol to a library using LCSC data."
    )
    parser.add_argument(
        "lcsc_ids", nargs="*", help="LCSC part ID(s), e.g. C25803"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing symbol with the same name",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting for missing values",
    )
    return parser.parse_args(argv)


def run_passive_creator(argv: list[str] | None = None) -> int:
    args = parse_passive_args(sys.argv[1:] if argv is None else argv)
    interactive = (
        not args.non_interactive
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )

    pending_ids = list(args.lcsc_ids)

    try:
        while True:
            if pending_ids:
                raw_id = pending_ids.pop(0)
            elif interactive:
                raw_id = prompt_text("LCSC ID (or 'q' to quit): ").strip()
                if not raw_id or raw_id.lower() == "q":
                    break
            else:
                break

            lcsc_id = raw_id.strip().upper()
            if not lcsc_id.startswith("C"):
                print(
                    f"Error: LCSC ID must start with C: {raw_id}",
                    file=sys.stderr,
                )
                if not interactive:
                    return 1
                continue

            try:
                plan = build_passive_plan(
                    lcsc_id, interactive=interactive
                )
            except ImportErrorWithExitCode as err:
                print(f"Error: {err}", file=sys.stderr)
                if not interactive:
                    return err.exit_code
                continue

            # --- summary ---
            print()
            print("Import summary:")
            print(
                f"  Symbol:       {plan.symbol_name} "
                f"(extends {plan.base_symbol.name})"
            )
            print(f"  Library:      {plan.library_name}")
            print(f"  Value:        {plan.value}")
            print(f"  Manufacturer: {plan.manufacturer}")
            print(f"  MPN:          {plan.mpn}")
            print(f"  LCSC ID:      {plan.lcsc_id}")
            print(f"  Datasheet:    {plan.datasheet or '~'}")
            print(f"  Description:  {plan.description}")
            print(f"  Package:      {plan.package}")
            if plan.spice_warning_override:
                print(
                    f"  SPICE Override: {plan.spice_warning_override}"
                )
            print()

            if interactive and not prompt_yes_no("Proceed?", default=True):
                continue

            try:
                apply_passive_plan(plan, overwrite=args.overwrite)
                print(f"Added {plan.symbol_name} to {plan.library_name}.")
            except ImportErrorWithExitCode as err:
                print(f"Error: {err}", file=sys.stderr)
                if not interactive:
                    return err.exit_code
                continue

            if not interactive and not pending_ids:
                break

            print()
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 1

    return 0
