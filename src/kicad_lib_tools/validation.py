"""Symbol field validation against the library conventions."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .config import get_config

REQUIRED_FIELDS = (
    "Reference",
    "Value",
    "Footprint",
    "Datasheet",
    "Description",
)

EASYEDA_LCSC_FIELD = "LCSC Part"
EASYEDA_MPN_FIELD = "Mfr. Part #"

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
    exclude_from_sim: bool | None
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
    exclude_from_sim: bool | None = None
    pin_count = 0
    extends: str | None = None
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()

        flag_match = FLAG_LINE.search(stripped)
        if flag_match and flag_match.group(1) == "in_bom":
            in_bom = flag_match.group(2) == "yes"
        if flag_match and flag_match.group(1) == "exclude_from_sim":
            exclude_from_sim = flag_match.group(2) == "yes"

        if stripped.startswith("(property"):
            prop_match = PROPERTY_START.search(stripped)
            if prop_match is not None:
                prop_name = prop_match.group(1)
            else:
                prop_quoted_values = QUOTED_STRING.findall("\n".join(lines[index : index + 3]))
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
        exclude_from_sim=exclude_from_sim,
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

    _resolve_inherited_flags(symbols)
    return symbols


def _resolve_inherited_flags(symbols: list[Symbol]) -> None:
    """Propagate ``exclude_from_sim`` from base to derived symbols."""
    by_name = {s.name: s for s in symbols}
    for symbol in symbols:
        if symbol.extends and symbol.exclude_from_sim is None:
            base = by_name.get(symbol.extends)
            if base is not None and base.exclude_from_sim is not None:
                symbol.exclude_from_sim = base.exclude_from_sim


def expand_paths(raw_paths: list[str]) -> list[Path]:
    """Return the symbol library files under ``raw_paths``, or all libraries if it is empty."""
    config = get_config()
    if not raw_paths:
        return sorted(config.symbol_path.rglob("*.kicad_sym"))

    files: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            repo_relative = config.repo_root / path
            if repo_relative.exists():
                path = repo_relative
        if path.is_dir():
            files.extend(sorted(path.rglob("*.kicad_sym")))
        elif path.suffix == ".kicad_sym" and path.is_file():
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
    effective_properties = dict(properties)
    names = get_config().fields
    disallowed_fields = {EASYEDA_LCSC_FIELD: names.lcsc_id, EASYEDA_MPN_FIELD: names.mpn}

    for disallowed, canonical in disallowed_fields.items():
        if disallowed in properties:
            issues.append(f'use "{canonical}" instead of "{disallowed}"')
            effective_properties.setdefault(canonical, properties[disallowed])

    override = properties.get(names.validation_override)
    if override is not None:
        if not override.hidden:
            issues.append("override field must be hidden")
        if override.value.strip() in {"", "~"}:
            issues.append("override field must include a reason")
    spice_warning_override = properties.get(names.spice_warning_override)
    if spice_warning_override is not None:
        if not spice_warning_override.hidden:
            issues.append("SPICE warning override field must be hidden")
        if spice_warning_override.value.strip() in {"", "~"}:
            issues.append("SPICE warning override field must include a reason")

    if override is not None:
        return issues, warnings

    missing_required = [field for field in REQUIRED_FIELDS if field not in effective_properties]
    if missing_required:
        issues.append(f"missing required fields: {', '.join(missing_required)}")

    if symbol.in_bom:
        missing_procurement = [
            field for field in names.procurement if field not in effective_properties
        ]
        if missing_procurement:
            issues.append(f"missing procurement fields: {', '.join(missing_procurement)}")

        not_hidden = [
            field
            for field in names.procurement
            if field in effective_properties and not effective_properties[field].hidden
        ]
        if not_hidden:
            issues.append(f"procurement fields must be hidden: {', '.join(not_hidden)}")

    has_sim_properties = any(name.startswith("Sim.") for name in properties)
    if (
        not has_sim_properties
        and not has_inferred_passive_spice_model(symbol)
        and not symbol.exclude_from_sim
        and spice_warning_override is None
    ):
        warnings.append("no SPICE model configured")

    return issues, warnings


@dataclass
class ValidationReport:
    """Validation issues and warnings for a set of symbol library files.

    Both maps go from a qualified symbol name to its messages.
    """

    file_count: int
    symbol_count: int = 0
    violations: dict[str, list[str]] = field(default_factory=dict)
    warnings: dict[str, list[str]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Whether no symbol has an issue."""
        return not self.violations

    def render(self) -> str:
        """Return the report as terminal text."""
        scope = f"{self.symbol_count} top-level symbols across {self.file_count} file(s)"
        warning_count = sum(len(messages) for messages in self.warnings.values())
        if self.violations:
            issue_count = sum(len(messages) for messages in self.violations.values())
            lines = ["Symbol field validation failed:", *_render_messages(self.violations)]
            lines += [
                "",
                f"Checked {scope}; found {issue_count} issue(s)"
                f" across {len(self.violations)} symbol(s).",
            ]
            if self.warnings:
                lines += ["", "Warnings:", *_render_messages(self.warnings), ""]
                lines.append(
                    f"Also found {warning_count} warning(s) across {len(self.warnings)} symbol(s)."
                )
            return "\n".join(lines)
        if self.warnings:
            lines = ["Symbol field validation passed with warnings:"]
            lines += _render_messages(self.warnings)
            lines += [
                "",
                f"Checked {scope}; found {warning_count} warning(s)"
                f" across {len(self.warnings)} symbol(s).",
            ]
            return "\n".join(lines)
        return f"Symbol field validation passed for {scope}."


def _render_messages(messages: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    for symbol_name, symbol_messages in messages.items():
        lines.append(f"  - {symbol_name}")
        lines.extend(f"    - {message}" for message in symbol_messages)
    return lines


def check_files(files: list[Path]) -> ValidationReport:
    """Validate every top-level symbol in ``files``."""
    report = ValidationReport(file_count=len(files))
    for path in files:
        for symbol in parse_symbol_file(path):
            report.symbol_count += 1
            issues, warnings = validate_symbol(symbol)
            if issues:
                report.violations.setdefault(symbol.qualified_name, []).extend(issues)
            if warnings:
                report.warnings.setdefault(symbol.qualified_name, []).extend(warnings)
    return report


def main(argv: list[str] | None = None) -> int:
    """Run ``kicad-lib validate`` and return its exit code."""
    parser = argparse.ArgumentParser(
        prog="kicad-lib validate",
        description="Validate KiCad symbol fields against the library conventions.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to validate. Defaults to the symbol directory.",
    )
    args = parser.parse_args(argv)

    files = expand_paths(args.paths)
    if not files and not args.paths:
        print("No symbol libraries to validate.")
        return 0
    if not files:
        print("No .kicad_sym files matched.", file=sys.stderr)
        return 1

    report = check_files(files)
    print(report.render())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
