#!/usr/bin/env python3
"""
Validate KiCad symbol fields against the repository README conventions.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
DEFAULT_SYMBOL_DIR = REPO_ROOT / "symbols"

REQUIRED_FIELDS = (
    "Reference",
    "Value",
    "Footprint",
    "Datasheet",
    "Description",
)

PROCUREMENT_FIELDS = (
    "Manufacturer",
    "Mfr. Part #",
    "LCSC ID",
    "Package",
)

OVERRIDE_FIELD = "Field Validation Override"
SPICE_WARNING_OVERRIDE_FIELD = "SPICE Warning Override"

DISALLOWED_FIELD_NAMES = {
    "LCSC Part": "LCSC ID",
}

TOP_LEVEL_SYMBOL_SUFFIX = re.compile(r"_[0-9]+_[0-9]+$")
SYMBOL_START = re.compile(r'\(symbol "([^"]+)"')
PROPERTY_START = re.compile(r'\(property "([^"]+)" "([^"]*)"')
QUOTED_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
FLAG_LINE = re.compile(r"\((in_bom|on_board|exclude_from_sim)\s+(yes|no)\)")


@dataclass
class Property:
    value: str
    hidden: bool


@dataclass
class Symbol:
    name: str
    path: Path
    in_bom: bool | None
    pin_count: int
    extends: str | None
    properties: dict[str, Property]

    @property
    def qualified_name(self) -> str:
        return f"{self.path.stem}:{self.name}"


def _block_depth_delta(line: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for char in line:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
    return depth


def parse_property(lines: list[str], start_index: int) -> tuple[Property, int]:
    depth = _block_depth_delta(lines[start_index])
    index = start_index + 1

    while index < len(lines) and depth > 0:
        depth += _block_depth_delta(lines[index])
        index += 1

    block_text = "\n".join(lines[start_index:index])
    match = PROPERTY_START.search(lines[start_index].strip())
    if match:
        value = match.group(2)
    else:
        quoted_values = QUOTED_STRING.findall(block_text)
        if len(quoted_values) < 2:
            raise ValueError("property block did not start with a property line")
        value = quoted_values[1]

    hidden = "(hide yes)" in block_text or " hide)" in block_text
    return Property(value=value, hidden=hidden), index


def parse_symbol_block(path: Path, name: str, lines: list[str]) -> Symbol:
    properties: dict[str, Property] = {}
    in_bom: bool | None = None
    pin_count = 0
    extends: str | None = None
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()

        flag_match = FLAG_LINE.search(stripped)
        if flag_match and flag_match.group(1) == "in_bom":
            in_bom = flag_match.group(2) == "yes"

        if stripped.startswith("(property"):
            prop_match = PROPERTY_START.search(stripped)
            if prop_match is not None:
                prop_name = prop_match.group(1)
            else:
                prop_quoted_values = QUOTED_STRING.findall("\n".join(lines[index: index + 3]))
                if not prop_quoted_values:
                    raise ValueError(f"failed to parse property line in {path}: {stripped}")
                prop_name = prop_quoted_values[0]
            property_value, next_index = parse_property(lines, index)
            properties[prop_name] = property_value
            index = next_index
            continue

        if stripped.startswith("(pin "):
            pin_count += 1
        elif stripped.startswith('(extends "'):
            quoted_values = QUOTED_STRING.findall(stripped)
            if quoted_values:
                extends = quoted_values[0]

        index += 1

    return Symbol(
        name=name,
        path=path,
        in_bom=in_bom,
        pin_count=pin_count,
        extends=extends,
        properties=properties,
    )


def has_inferred_passive_spice_model(symbol: Symbol) -> bool:
    reference = symbol.properties.get("Reference")
    if reference is None:
        return False
    return reference.value in {"R", "C", "L"} and (
        symbol.pin_count == 2 or symbol.extends is not None
    )


def parse_symbol_file(path: Path) -> list[Symbol]:
    lines = path.read_text(encoding="utf-8").splitlines()
    symbols: list[Symbol] = []
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        match = SYMBOL_START.search(stripped)
        if match is None:
            index += 1
            continue

        name = match.group(1)
        depth = _block_depth_delta(lines[index])
        block = [lines[index]]
        index += 1

        while index < len(lines) and depth > 0:
            block.append(lines[index])
            depth += _block_depth_delta(lines[index])
            index += 1

        if TOP_LEVEL_SYMBOL_SUFFIX.search(name):
            continue

        symbols.append(parse_symbol_block(path, name, block))

    return symbols


def expand_paths(raw_paths: list[str]) -> list[Path]:
    if not raw_paths:
        return sorted(DEFAULT_SYMBOL_DIR.rglob("*.kicad_sym"))

    files: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            repo_relative = REPO_ROOT / path
            if repo_relative.exists():
                path = repo_relative
        if path.is_dir():
            files.extend(sorted(path.rglob("*.kicad_sym")))
        elif path.suffix == ".kicad_sym":
            files.append(path)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for file_path in files:
        resolved = file_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(file_path)

    return deduped


def validate_symbol(symbol: Symbol) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    properties = symbol.properties

    for disallowed, canonical in DISALLOWED_FIELD_NAMES.items():
        if disallowed in properties:
            issues.append(f'use "{canonical}" instead of "{disallowed}"')

    override = properties.get(OVERRIDE_FIELD)
    if override is not None:
        if not override.hidden:
            issues.append("override field must be hidden")
        if override.value.strip() in {"", "~"}:
            issues.append("override field must include a reason")
    spice_warning_override = properties.get(SPICE_WARNING_OVERRIDE_FIELD)
    if spice_warning_override is not None:
        if not spice_warning_override.hidden:
            issues.append("SPICE warning override field must be hidden")
        if spice_warning_override.value.strip() in {"", "~"}:
            issues.append("SPICE warning override field must include a reason")

    if override is not None:
        return issues, warnings

    missing_required = [field for field in REQUIRED_FIELDS if field not in properties]
    if missing_required:
        issues.append(f"missing required fields: {', '.join(missing_required)}")

    if symbol.in_bom:
        missing_procurement = [
            field for field in PROCUREMENT_FIELDS if field not in properties
        ]
        if missing_procurement:
            issues.append(
                f"missing procurement fields: {', '.join(missing_procurement)}"
            )

        not_hidden = [
            field
            for field in PROCUREMENT_FIELDS
            if field in properties and not properties[field].hidden
        ]
        if not_hidden:
            issues.append(f"procurement fields must be hidden: {', '.join(not_hidden)}")

    has_sim_properties = any(name.startswith("Sim.") for name in properties)
    if (
        not has_sim_properties
        and not has_inferred_passive_spice_model(symbol)
        and spice_warning_override is None
    ):
        warnings.append("no SPICE model configured")

    return issues, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate KiCad symbol fields against the README conventions."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to validate. Defaults to symbols/.",
    )
    args = parser.parse_args(argv)

    files = expand_paths(args.paths)
    if not files:
        print("No .kicad_sym files matched.", file=sys.stderr)
        return 1

    violations: dict[str, list[str]] = {}
    warning_map: dict[str, list[str]] = {}
    symbol_count = 0

    for path in files:
        for symbol in parse_symbol_file(path):
            symbol_count += 1
            issues, warnings = validate_symbol(symbol)
            if not issues:
                if warnings:
                    warning_map.setdefault(symbol.qualified_name, []).extend(warnings)
                continue
            violations.setdefault(symbol.qualified_name, []).extend(issues)
            if warnings:
                warning_map.setdefault(symbol.qualified_name, []).extend(warnings)

    if violations:
        print("Symbol field validation failed:")
        issue_count = 0
        for symbol_name, issues in violations.items():
            print(f"  - {symbol_name}")
            for issue in issues:
                print(f"    - {issue}")
                issue_count += 1
        print()
        print(
            f"Checked {symbol_count} top-level symbols across {len(files)} file(s); "
            f"found {issue_count} issue(s) across {len(violations)} symbol(s)."
        )
        if warning_map:
            print()
            print("Warnings:")
            warning_count = 0
            for symbol_name, warnings in warning_map.items():
                print(f"  - {symbol_name}")
                for warning in warnings:
                    print(f"    - {warning}")
                    warning_count += 1
            print()
            print(
                f"Also found {warning_count} warning(s) across {len(warning_map)} symbol(s)."
            )
        return 1

    if warning_map:
        print("Symbol field validation passed with warnings:")
        warning_count = 0
        for symbol_name, warnings in warning_map.items():
            print(f"  - {symbol_name}")
            for warning in warnings:
                print(f"    - {warning}")
                warning_count += 1
        print()
        print(
            f"Checked {symbol_count} top-level symbols across {len(files)} file(s); "
            f"found {warning_count} warning(s) across {len(warning_map)} symbol(s)."
        )
        return 0

    print(
        f"Symbol field validation passed for {symbol_count} top-level symbols "
        f"across {len(files)} file(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
