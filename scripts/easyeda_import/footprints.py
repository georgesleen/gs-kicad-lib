from __future__ import annotations

import re
import shutil
from pathlib import Path

from .errors import ImportErrorWithExitCode
from .paths import display_path, escape_kicad_string


KICAD_FOOTPRINT_START = re.compile(r'\(footprint\s+"([^"]+)"')
LEGACY_MODULE_START = re.compile(r"\(module\s+([^\s)]+)")


def _normalize_footprint_name(raw_name: str) -> str:
    return raw_name.split(":")[-1]


def parse_footprint_name(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        match = KICAD_FOOTPRINT_START.match(stripped)
        if match:
            return _normalize_footprint_name(match.group(1))
        match = LEGACY_MODULE_START.match(stripped)
        if match:
            return _normalize_footprint_name(match.group(1))
    raise ImportErrorWithExitCode(
        f"failed to parse footprint name from {path}", exit_code=3
    )


def rewrite_model_paths(footprint_text: str, model_reference_paths: list[str]) -> str:
    lines = footprint_text.splitlines(keepends=True)
    updated_lines: list[str] = []
    model_index = 0
    skipping_model_block = False
    model_block_depth = 0

    for line in lines:
        if skipping_model_block:
            model_block_depth += line.count("(") - line.count(")")
            if model_block_depth <= 0:
                skipping_model_block = False
            continue

        match = re.match(r'(\s*\(model\s+")([^"]+)(".*)', line)
        if match:
            if not model_reference_paths:
                skipping_model_block = True
                model_block_depth = line.count("(") - line.count(")")
                if model_block_depth <= 0:
                    skipping_model_block = False
                continue
            replacement_path = model_reference_paths[
                min(model_index, len(model_reference_paths) - 1)
            ]
            updated_lines.append(
                f'{match.group(1)}{escape_kicad_string(replacement_path)}{match.group(3)}\n'
            )
            model_index += 1
        else:
            updated_lines.append(line)

    return "".join(updated_lines)


def ensure_writable_path(destination: Path, overwrite: bool, collision_label: str) -> None:
    if destination.exists() and not overwrite:
        raise ImportErrorWithExitCode(
            f"{collision_label} already exists at {display_path(destination)}; use the matching overwrite flag to replace it",
            exit_code=4,
        )


def copy_file(source: Path, destination: Path, overwrite: bool, collision_label: str) -> None:
    ensure_writable_path(destination, overwrite, collision_label)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def write_footprint(destination: Path, content: str, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        raise ImportErrorWithExitCode(
            f"footprint already exists at {display_path(destination)}; use --overwrite-footprint to replace it",
            exit_code=4,
        )
    destination.write_text(content, encoding="utf-8")
