from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import get_config
from .errors import ImportErrorWithExitCode
from .paths import (
    PROPERTY_FONT_SIZE,
    block_depth_delta,
    display_path,
    ensure_trailing_newline,
    escape_kicad_string,
)

SYMBOL_START = re.compile(r'\(symbol "([^"]+)"')
PROPERTY_INLINE_START = re.compile(r'\(property "([^"]+)" "([^"]*)"')
QUOTED_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


@dataclass
class SymbolBlock:
    name: str
    start: int
    end: int
    text: str


@dataclass
class PropertyBlock:
    name: str
    start: int
    end: int
    value: str
    hidden: bool


def extract_single_symbol(path: Path) -> SymbolBlock:
    text = path.read_text(encoding="utf-8")
    symbols = parse_top_level_symbols(text)
    if len(symbols) != 1:
        raise ImportErrorWithExitCode(
            f"expected exactly one top-level symbol in {path}, found {len(symbols)}",
            exit_code=3,
        )
    return symbols[0]


def parse_top_level_symbols(text: str) -> list[SymbolBlock]:
    lines = text.splitlines(keepends=True)
    symbols: list[SymbolBlock] = []
    index = 0
    depth = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if depth == 1:
            match = SYMBOL_START.match(stripped)
            if match:
                block_start = index
                block_depth = block_depth_delta(line)
                index += 1
                while index < len(lines) and block_depth > 0:
                    block_depth += block_depth_delta(lines[index])
                    index += 1
                symbols.append(
                    SymbolBlock(
                        name=match.group(1),
                        start=block_start,
                        end=index,
                        text="".join(lines[block_start:index]),
                    )
                )
                continue
        depth += block_depth_delta(line)
        index += 1

    return symbols


def parse_symbol_properties(symbol_text: str) -> list[PropertyBlock]:
    lines = symbol_text.splitlines(keepends=True)
    properties: list[PropertyBlock] = []
    index = 0
    depth = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if depth == 1 and stripped.startswith("(property"):
            property_block, index = parse_property_block(lines, index)
            properties.append(property_block)
            continue
        depth += block_depth_delta(line)
        index += 1
    return properties


def parse_property_block(lines: list[str], start_index: int) -> tuple[PropertyBlock, int]:
    block_start = start_index
    block_depth = block_depth_delta(lines[start_index])
    index = start_index + 1
    while index < len(lines) and block_depth > 0:
        block_depth += block_depth_delta(lines[index])
        index += 1

    block_lines = lines[block_start:index]
    block_text = "".join(block_lines)
    inline_match = PROPERTY_INLINE_START.match(block_lines[0].strip())
    if inline_match is not None:
        name = inline_match.group(1)
        value = inline_match.group(2)
    else:
        quoted_values = QUOTED_STRING.findall(block_text)
        if len(quoted_values) < 2:
            raise ImportErrorWithExitCode(
                f"failed to parse property block: {block_lines[0].strip()}",
                exit_code=3,
            )
        name = quoted_values[0]
        value = quoted_values[1]

    return (
        PropertyBlock(
            name=name,
            start=block_start,
            end=index,
            value=value,
            hidden="(hide yes)" in block_text or " hide)" in block_text,
        ),
        index,
    )


def get_first_property_value(properties: list[PropertyBlock], name: str) -> str:
    for prop in properties:
        if prop.name == name:
            return prop.value
    return ""


def property_value_or_blank(property_block: PropertyBlock | None) -> str:
    return property_block.value if property_block is not None else ""


def prepare_symbol_block(
    symbol_block: str,
    footprint_ref: str,
    datasheet: str,
    description: str,
    manufacturer: str,
    mpn: str,
    lcsc_id: str,
    package: str,
    validation_override: str,
    spice_warning_override: str,
) -> str:
    updated = symbol_block
    updated = delete_property(updated, "LCSC Part")
    updated = delete_property(updated, "Mfr. Part #")
    updated = upsert_property(updated, "Footprint", footprint_ref, hidden=True)
    updated = upsert_property(updated, "Datasheet", datasheet or "~", hidden=True)
    updated = upsert_property(updated, "Description", description, hidden=True)
    if manufacturer:
        updated = upsert_property(updated, "Manufacturer", manufacturer, hidden=True)
    if mpn:
        updated = upsert_property(updated, "MPN", mpn, hidden=True)
    updated = upsert_property(updated, "LCSC ID", lcsc_id, hidden=True)
    if package:
        updated = upsert_property(updated, "Package", package, hidden=True)
    if validation_override:
        updated = upsert_property(
            updated, "Field Validation Override", validation_override, hidden=True
        )
    else:
        updated = delete_property(updated, "Field Validation Override")
    if spice_warning_override:
        updated = upsert_property(
            updated, "SPICE Warning Override", spice_warning_override, hidden=True
        )
    else:
        updated = delete_property(updated, "SPICE Warning Override")
    return ensure_trailing_newline(updated)


def sanitize_symbol_name(name: str) -> str:
    """Return ``name`` with slashes and whitespace runs replaced by underscores."""
    return re.sub(r"[/\s]+", "_", name.strip())


def rename_symbol(symbol_block: str, old_name: str, new_name: str) -> str:
    """Return a top-level symbol block renamed from ``old_name`` to ``new_name``.

    The rename covers the block itself and its ``<name>_<unit>_<style>`` unit symbols.
    """
    pattern = re.compile(r'\(symbol "' + re.escape(old_name) + r'((?:_\d+_\d+)?)"')
    return pattern.sub(lambda match: f'(symbol "{new_name}{match.group(1)}"', symbol_block)


def upsert_property(symbol_block: str, name: str, value: str, hidden: bool) -> str:
    lines = symbol_block.splitlines(keepends=True)
    properties = parse_symbol_properties(symbol_block)
    matches = [prop for prop in properties if prop.name == name]
    new_lines = build_property_block(name=name, value=value, hidden=hidden).splitlines(
        keepends=True
    )

    if matches:
        first_start = matches[0].start
        for prop in reversed(matches):
            del lines[prop.start : prop.end]
        lines[first_start:first_start] = new_lines
        return "".join(lines)

    insert_index = find_symbol_property_insert_index(lines)
    lines[insert_index:insert_index] = new_lines
    return "".join(lines)


def delete_property(symbol_block: str, name: str) -> str:
    lines = symbol_block.splitlines(keepends=True)
    properties = [prop for prop in parse_symbol_properties(symbol_block) if prop.name == name]
    for prop in reversed(properties):
        del lines[prop.start : prop.end]
    return "".join(lines)


def find_symbol_property_insert_index(lines: list[str]) -> int:
    depth = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if depth == 1 and stripped.startswith('(symbol "'):
            return index
        depth += block_depth_delta(line)
    return len(lines) - 1


def build_property_block(name: str, value: str, hidden: bool) -> str:
    hide_line = "\n\t\t\t\t(hide yes)" if hidden else ""
    return (
        f'\t\t(property "{escape_kicad_string(name)}" "{escape_kicad_string(value)}"\n'
        "\t\t\t(at 0 0 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        f"\t\t\t\t\t(size {PROPERTY_FONT_SIZE} {PROPERTY_FONT_SIZE})\n"
        "\t\t\t\t)"
        f"{hide_line}\n"
        "\t\t\t)\n"
        "\t\t)\n"
    )


def render_symbol_library_update(
    symbol_library_path: Path,
    symbol_name: str,
    symbol_block: str,
    overwrite: bool,
) -> str:
    text = symbol_library_path.read_text(encoding="utf-8")
    symbols = parse_top_level_symbols(text)
    lines = text.splitlines(keepends=True)
    matches = [symbol for symbol in symbols if symbol.name == symbol_name]
    new_block_lines = ensure_trailing_newline(symbol_block).splitlines(keepends=True)

    if matches and not overwrite:
        raise ImportErrorWithExitCode(
            f"symbol {symbol_name} already exists in"
            f" {display_path(symbol_library_path)}; use --overwrite-symbol to replace it",
            exit_code=4,
        )

    if matches:
        for symbol in reversed(matches[1:]):
            del lines[symbol.start : symbol.end]
        first = matches[0]
        del lines[first.start : first.end]
        lines[first.start : first.start] = new_block_lines
    else:
        insert_index = find_symbol_library_insert_index(lines)
        lines[insert_index:insert_index] = new_block_lines

    return "".join(lines)


def remove_symbol_from_library_text(text: str, symbol_name: str) -> str:
    """Return a symbol library's text without its top-level symbols named ``symbol_name``.

    Raises:
        ImportErrorWithExitCode: if the library has no symbol with that name.
    """
    matches = [symbol for symbol in parse_top_level_symbols(text) if symbol.name == symbol_name]
    if not matches:
        raise ImportErrorWithExitCode(f"symbol {symbol_name} not found", exit_code=3)
    lines = text.splitlines(keepends=True)
    for symbol in reversed(matches):
        del lines[symbol.start : symbol.end]
    return "".join(lines)


def find_symbol_library_insert_index(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip() == ")":
            return index
    raise ImportErrorWithExitCode("malformed KiCad symbol library file", exit_code=3)


def validate_symbol_library_text(symbol_target: Path, content: str, verbose: bool) -> None:
    temp_path = get_config().tmp_path / ".validate" / symbol_target.name
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(content, encoding="utf-8")
    result = run_symbol_validator(temp_path)
    if verbose and result.stdout.strip():
        print("Validator stdout:")
        print(result.stdout.rstrip())
    if verbose and result.stderr.strip():
        print("Validator stderr:")
        print(result.stderr.rstrip())
    if result.returncode != 0:
        details = result.stdout.strip() or result.stderr.strip() or "validation failed"
        raise ImportErrorWithExitCode(details, exit_code=5)


def run_symbol_validator(symbol_library: Path) -> subprocess.CompletedProcess[str]:
    """Run the field validator script on one symbol library and return its result."""
    config = get_config()
    return subprocess.run(
        [sys.executable, str(config.validator_script_path), str(symbol_library)],
        cwd=config.repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
