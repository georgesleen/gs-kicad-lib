#!/usr/bin/env python3
"""
Import an EasyEDA/LCSC part into this repository's KiCad libraries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
SYMBOL_DIR = REPO_ROOT / "symbols"
FOOTPRINT_DIR = REPO_ROOT / "footprints"
MODEL_ROOT = REPO_ROOT / "3d-models"
TMP_ROOT = REPO_ROOT / "tmp" / "easyeda-import"
STATE_FILE = REPO_ROOT / "tmp" / "easyeda-import-state.json"
SETUP_KICAD_SCRIPT = REPO_ROOT / "scripts" / "setup-kicad.sh"
VALIDATOR_SCRIPT = REPO_ROOT / "scripts" / "check-symbol-fields.py"
DEFAULT_CONVERTER = (
    REPO_ROOT.parent / "easyeda2kicad.py" / ".venv" / "bin" / "python"
)
SYMBOL_START = re.compile(r'\(symbol "([^"]+)"')
PROPERTY_START = re.compile(r'\(property "([^"]+)" "([^"]*)"')
FOOTPRINT_START = re.compile(r'\(footprint "([^"]+)"')
VALID_LIBRARY_NAME = re.compile(r"^GS_[A-Za-z0-9][A-Za-z0-9_+-]*$")
PROPERTY_FONT_SIZE = 1.27
PROCUREMENT_FIELDS = {"Manufacturer", "Mfr. Part #", "LCSC ID", "Package"}
HIDDEN_FIELDS = {
    "Footprint",
    "Datasheet",
    "Description",
    "Manufacturer",
    "Mfr. Part #",
    "LCSC ID",
    "Package",
    "Field Validation Override",
}
MODEL_EXTENSIONS = {".step", ".stp", ".wrl"}


class ImportErrorWithExitCode(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a part from easyeda2kicad into this repo's KiCad libraries."
    )
    parser.add_argument("--lcsc-id", help="LCSC part ID, for example C2040")
    parser.add_argument("--symbol-lib", help="Target symbol library, for example GS_IC")
    parser.add_argument(
        "--footprint-lib", help="Target footprint library, for example GS_Connectors"
    )
    parser.add_argument(
        "--models-dir",
        help="Model destination directory. Defaults to 3d-models/",
    )
    parser.add_argument("--manufacturer", help="Manufacturer symbol field value")
    parser.add_argument("--mfr-part", help="Mfr. Part # symbol field value")
    parser.add_argument("--datasheet", help="Datasheet symbol field value")
    parser.add_argument("--package", help="Package symbol field value")
    parser.add_argument(
        "--field-validation-override",
        help="Optional Field Validation Override reason",
    )
    parser.add_argument(
        "--converter-command",
        help="Command used to run the converter. Defaults to the sibling easyeda2kicad fork.",
    )
    parser.add_argument(
        "--name",
        help="Optional staging directory name. Defaults to a slug derived from the LCSC ID.",
    )
    parser.add_argument(
        "--overwrite-symbol",
        action="store_true",
        help="Replace an existing symbol with the same name",
    )
    parser.add_argument(
        "--overwrite-footprint",
        action="store_true",
        help="Replace an existing footprint with the same filename",
    )
    parser.add_argument(
        "--overwrite-models",
        action="store_true",
        help="Replace existing 3D models with the same filename",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting for missing values",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print converter command and validation details",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        run_import(args)
    except ImportErrorWithExitCode as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except KeyboardInterrupt:
        print("Error: cancelled by user", file=sys.stderr)
        return 1
    return 0


def run_import(args: argparse.Namespace) -> None:
    state = load_state()
    interactive = not args.non_interactive and sys.stdin.isatty() and sys.stdout.isatty()

    lcsc_id = normalize_lcsc_id(
        resolve_text_value(
            args.lcsc_id,
            prompt="LCSC ID",
            interactive=interactive,
            allow_blank=False,
        )
    )
    symbol_lib = resolve_library_name(
        provided=args.symbol_lib,
        prompt_name="symbol",
        existing=list_symbol_libraries(),
        default=state.get("last_symbol_lib"),
        interactive=interactive,
    )
    footprint_lib = resolve_library_name(
        provided=args.footprint_lib,
        prompt_name="footprint",
        existing=list_footprint_libraries(),
        default=state.get("last_footprint_lib"),
        interactive=interactive,
    )
    models_dir = resolve_models_dir(
        provided=args.models_dir,
        default=state.get("last_models_dir", str(MODEL_ROOT.relative_to(REPO_ROOT))),
        interactive=interactive,
    )

    stage_name = args.name or slugify(lcsc_id)
    stage_dir = TMP_ROOT / stage_name
    output_base = stage_dir / "generated"
    reset_stage_dir(stage_dir)

    converter_command = resolve_converter_command(args.converter_command)
    converter_result = run_converter(
        converter_command=converter_command,
        lcsc_id=lcsc_id,
        output_base=output_base,
        verbose=args.verbose,
    )

    staged_symbol_path = output_base.with_suffix(".kicad_sym")
    staged_footprint_dir = output_base.with_suffix(".pretty")
    staged_model_dir = output_base

    if not staged_symbol_path.is_file():
        raise ImportErrorWithExitCode(
            f"converter did not produce {staged_symbol_path}", exit_code=3
        )
    if not staged_footprint_dir.is_dir():
        raise ImportErrorWithExitCode(
            f"converter did not produce {staged_footprint_dir}", exit_code=3
        )

    symbol_block = extract_single_symbol(staged_symbol_path)
    staged_properties = parse_symbol_properties(symbol_block.text)
    staged_property_map = {prop.name: prop for prop in staged_properties}

    footprint_files = sorted(staged_footprint_dir.glob("*.kicad_mod"))
    if len(footprint_files) != 1:
        raise ImportErrorWithExitCode(
            f"expected exactly one staged footprint, found {len(footprint_files)}",
            exit_code=3,
        )
    staged_footprint_path = footprint_files[0]
    footprint_name = parse_footprint_name(staged_footprint_path)
    staged_model_paths = sorted(
        path
        for path in staged_model_dir.iterdir()
        if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS
    )

    manufacturer = resolve_metadata_value(
        provided=args.manufacturer,
        prompt="Manufacturer",
        default=get_first_property_value(staged_properties, "Manufacturer"),
        interactive=interactive,
        required=not args.field_validation_override,
    )
    datasheet = resolve_metadata_value(
        provided=args.datasheet,
        prompt="Datasheet",
        default=property_value_or_blank(staged_property_map.get("Datasheet")),
        interactive=interactive,
        required=False,
    )
    mfr_part = resolve_metadata_value(
        provided=args.mfr_part,
        prompt="Mfr. Part #",
        default="",
        interactive=interactive,
        required=not args.field_validation_override,
    )
    package = resolve_metadata_value(
        provided=args.package,
        prompt="Package",
        default=footprint_name,
        interactive=interactive,
        required=not args.field_validation_override,
    )
    validation_override = resolve_metadata_value(
        provided=args.field_validation_override,
        prompt="Field Validation Override reason",
        default="",
        interactive=interactive,
        required=False,
    )

    if not validation_override:
        missing = [
            name
            for name, value in {
                "Manufacturer": manufacturer,
                "Mfr. Part #": mfr_part,
                "Package": package,
            }.items()
            if not value
        ]
        if missing:
            raise ImportErrorWithExitCode(
                "missing required symbol fields: " + ", ".join(missing), exit_code=1
            )

    symbol_target = SYMBOL_DIR / f"{symbol_lib}.kicad_sym"
    footprint_dir = FOOTPRINT_DIR / f"{footprint_lib}.pretty"

    created_symbol_lib = ensure_symbol_library(symbol_target, interactive)
    created_footprint_lib = ensure_footprint_library(footprint_dir, interactive)
    models_dir.mkdir(parents=True, exist_ok=True)

    prepared_symbol = prepare_symbol_block(
        symbol_block=symbol_block.text,
        footprint_ref=f"{footprint_lib}:{footprint_name}",
        datasheet=datasheet or "~",
        manufacturer=manufacturer,
        mfr_part=mfr_part,
        lcsc_id=lcsc_id,
        package=package,
        validation_override=validation_override,
    )
    rendered_symbol_library = render_symbol_library_update(
        symbol_library_path=symbol_target,
        symbol_name=symbol_block.name,
        symbol_block=prepared_symbol,
        overwrite=args.overwrite_symbol,
    )
    validate_symbol_library_text(
        symbol_target=symbol_target,
        content=rendered_symbol_library,
        verbose=args.verbose,
    )

    footprint_destination = footprint_dir / staged_footprint_path.name
    ensure_writable_path(
        destination=footprint_destination,
        overwrite=args.overwrite_footprint,
        collision_label="footprint",
    )
    for staged_model in staged_model_paths:
        ensure_writable_path(
            destination=models_dir / staged_model.name,
            overwrite=args.overwrite_models,
            collision_label=f"3D model {staged_model.name}",
        )

    imported_models: list[tuple[Path, str]] = []
    for staged_model in staged_model_paths:
        destination = models_dir / staged_model.name
        copy_file(
            source=staged_model,
            destination=destination,
            overwrite=args.overwrite_models,
            collision_label=f"3D model {staged_model.name}",
        )
        imported_models.append((destination, model_reference_path(destination)))

    footprint_text = staged_footprint_path.read_text(encoding="utf-8")
    footprint_text = rewrite_model_paths(
        footprint_text=footprint_text,
        model_reference_paths=[ref for _dest, ref in imported_models],
    )
    write_footprint(
        destination=footprint_destination,
        content=footprint_text,
        overwrite=args.overwrite_footprint,
    )

    symbol_target.write_text(rendered_symbol_library, encoding="utf-8")
    save_state(
        {
            "last_symbol_lib": symbol_lib,
            "last_footprint_lib": footprint_lib,
            "last_models_dir": models_dir_state_value(models_dir),
        }
    )

    print(f"Imported {symbol_block.name} from {lcsc_id}")
    print(f"  symbol: {symbol_target.relative_to(REPO_ROOT)}")
    print(f"  footprint: {footprint_destination.relative_to(REPO_ROOT)}")
    if imported_models:
        print("  models:")
        for destination, _reference in imported_models:
            print(f"    {destination.relative_to(REPO_ROOT)}")
    else:
        print("  models: none")
    print(f"  staging: {stage_dir.relative_to(REPO_ROOT)}")
    if args.verbose and converter_result.stdout.strip():
        print("Converter stdout:")
        print(converter_result.stdout.rstrip())
    if args.verbose and converter_result.stderr.strip():
        print("Converter stderr:")
        print(converter_result.stderr.rstrip())

    if created_symbol_lib or created_footprint_lib:
        offer_setup_kicad(interactive=interactive)


def reset_stage_dir(stage_dir: Path) -> None:
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)


def resolve_converter_command(provided: str | None) -> str:
    if provided:
        return provided
    env_value = os.environ.get("GS_EASYEDA2KICAD_CMD")
    if env_value:
        return env_value
    if DEFAULT_CONVERTER.is_file():
        return f"{DEFAULT_CONVERTER} -m easyeda2kicad"
    return "easyeda2kicad"


def run_converter(
    converter_command: str, lcsc_id: str, output_base: Path, verbose: bool
) -> subprocess.CompletedProcess[str]:
    command = shlex.split(converter_command) + [
        "--full",
        f"--lcsc_id={lcsc_id}",
        f"--output={output_base}",
    ]
    if verbose:
        print("Running converter:")
        print("  " + " ".join(shlex.quote(part) for part in command))
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as err:
        raise ImportErrorWithExitCode(
            f"converter command not found: {converter_command}", exit_code=1
        ) from err

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ImportErrorWithExitCode(
            f"converter failed with exit code {result.returncode}: {details}",
            exit_code=2,
        )
    return result


def normalize_lcsc_id(raw_value: str) -> str:
    value = raw_value.strip().upper()
    if not value.startswith("C"):
        raise ImportErrorWithExitCode("LCSC ID must start with C", exit_code=1)
    return value


def list_symbol_libraries() -> list[str]:
    return sorted(path.stem for path in SYMBOL_DIR.glob("*.kicad_sym"))


def list_footprint_libraries() -> list[str]:
    return sorted(path.stem for path in FOOTPRINT_DIR.glob("*.pretty"))


def resolve_library_name(
    provided: str | None,
    prompt_name: str,
    existing: list[str],
    default: str | None,
    interactive: bool,
) -> str:
    if provided:
        return normalize_library_name(provided)
    if not interactive:
        raise ImportErrorWithExitCode(
            f"missing --{prompt_name}-lib in non-interactive mode", exit_code=1
        )
    libraries_preview = ", ".join(existing[:8])
    if len(existing) > 8:
        libraries_preview += ", ..."
    if libraries_preview:
        print(f"Available {prompt_name} libraries: {libraries_preview}")
    while True:
        response = prompt_text(
            f"Target {prompt_name} library"
            + (f" [{default}]" if default else "")
            + ": "
        ).strip()
        if not response and default:
            response = default
        if not response:
            print("A library name is required.")
            continue
        try:
            return normalize_library_name(response)
        except ImportErrorWithExitCode as err:
            print(err)


def normalize_library_name(raw_name: str) -> str:
    value = raw_name.strip()
    if value.endswith(".kicad_sym"):
        value = value[: -len(".kicad_sym")]
    if value.endswith(".pretty"):
        value = value[: -len(".pretty")]
    if not VALID_LIBRARY_NAME.fullmatch(value):
        raise ImportErrorWithExitCode(
            f'invalid library name "{raw_name}": expected GS_<Category>',
            exit_code=1,
        )
    return value


def resolve_models_dir(
    provided: str | None, default: str, interactive: bool
) -> Path:
    raw_value = provided
    if not raw_value and interactive:
        response = prompt_text(f"3D model directory [{default}]: ").strip()
        raw_value = response or default
    if not raw_value:
        raw_value = default
    path = Path(raw_value)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def resolve_text_value(
    provided: str | None,
    prompt: str,
    interactive: bool,
    allow_blank: bool,
) -> str:
    if provided is not None:
        return provided
    if not interactive:
        raise ImportErrorWithExitCode(
            f"missing required value for {prompt.lower()}", exit_code=1
        )
    while True:
        response = prompt_text(f"{prompt}: ")
        if response or allow_blank:
            return response
        print(f"{prompt} is required.")


def resolve_metadata_value(
    provided: str | None,
    prompt: str,
    default: str,
    interactive: bool,
    required: bool,
) -> str:
    if provided is not None:
        return provided.strip()
    if not interactive:
        return default.strip()
    while True:
        response = prompt_text(
            f"{prompt}" + (f" [{default}]" if default else "") + ": "
        ).strip()
        if response:
            return response
        if default:
            return default.strip()
        if not required:
            return ""
        print(f"{prompt} is required.")


def prompt_text(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError as err:
        raise ImportErrorWithExitCode("interactive input cancelled", exit_code=1) from err


def prompt_yes_no(prompt: str, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = prompt_text(f"{prompt} {suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def ensure_symbol_library(path: Path, interactive: bool) -> bool:
    if path.exists():
        return False
    if not interactive:
        raise ImportErrorWithExitCode(
            f"symbol library does not exist: {path.relative_to(REPO_ROOT)}",
            exit_code=1,
        )
    if not prompt_yes_no(
        f"Create symbol library {path.relative_to(REPO_ROOT)}?", default=True
    ):
        raise ImportErrorWithExitCode("symbol library creation declined", exit_code=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "(kicad_symbol_lib\n"
        '\t(version 20241209)\n'
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "9.0")\n'
        ")\n",
        encoding="utf-8",
    )
    return True


def ensure_footprint_library(path: Path, interactive: bool) -> bool:
    if path.exists():
        return False
    if not interactive:
        raise ImportErrorWithExitCode(
            f"footprint library does not exist: {path.relative_to(REPO_ROOT)}",
            exit_code=1,
        )
    if not prompt_yes_no(
        f"Create footprint library {path.relative_to(REPO_ROOT)}?", default=True
    ):
        raise ImportErrorWithExitCode("footprint library creation declined", exit_code=1)
    path.mkdir(parents=True, exist_ok=True)
    return True


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
        if depth == 1 and stripped.startswith('(property "'):
            match = PROPERTY_START.match(stripped)
            if match is None:
                raise ImportErrorWithExitCode(
                    f"failed to parse property line: {stripped}", exit_code=3
                )
            block_start = index
            block_depth = block_depth_delta(line)
            hidden = False
            index += 1
            while index < len(lines) and block_depth > 0:
                hidden = hidden or "(hide yes)" in lines[index]
                block_depth += block_depth_delta(lines[index])
                index += 1
            properties.append(
                PropertyBlock(
                    name=match.group(1),
                    start=block_start,
                    end=index,
                    value=match.group(2),
                    hidden=hidden,
                )
            )
            continue
        depth += block_depth_delta(line)
        index += 1
    return properties


def parse_footprint_name(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = FOOTPRINT_START.match(line.strip())
        if match:
            return match.group(1)
    raise ImportErrorWithExitCode(
        f"failed to parse footprint name from {path}", exit_code=3
    )


def prepare_symbol_block(
    symbol_block: str,
    footprint_ref: str,
    datasheet: str,
    manufacturer: str,
    mfr_part: str,
    lcsc_id: str,
    package: str,
    validation_override: str,
) -> str:
    updated = symbol_block
    updated = delete_property(updated, "LCSC Part")
    updated = upsert_property(updated, "Footprint", footprint_ref, hidden=True)
    updated = upsert_property(updated, "Datasheet", datasheet or "~", hidden=True)
    if manufacturer:
        updated = upsert_property(updated, "Manufacturer", manufacturer, hidden=True)
    if mfr_part:
        updated = upsert_property(updated, "Mfr. Part #", mfr_part, hidden=True)
    updated = upsert_property(updated, "LCSC ID", lcsc_id, hidden=True)
    if package:
        updated = upsert_property(updated, "Package", package, hidden=True)
    if validation_override:
        updated = upsert_property(
            updated, "Field Validation Override", validation_override, hidden=True
        )
    else:
        updated = delete_property(updated, "Field Validation Override")
    return ensure_trailing_newline(updated)


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
            f"symbol {symbol_name} already exists in {symbol_library_path.relative_to(REPO_ROOT)}; use --overwrite-symbol to replace it",
            exit_code=4,
        )

    if matches:
        for symbol in reversed(matches[1:]):
            del lines[symbol.start : symbol.end]
        first = matches[0]
        del lines[first.start : first.end]
        lines[first.start:first.start] = new_block_lines
    else:
        insert_index = find_symbol_library_insert_index(lines)
        lines[insert_index:insert_index] = new_block_lines

    return "".join(lines)


def find_symbol_library_insert_index(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip() == ")":
            return index
    raise ImportErrorWithExitCode("malformed KiCad symbol library file", exit_code=3)


def rewrite_model_paths(footprint_text: str, model_reference_paths: list[str]) -> str:
    if not model_reference_paths:
        return footprint_text

    lines = footprint_text.splitlines(keepends=True)
    updated_lines: list[str] = []
    model_index = 0

    for line in lines:
        match = re.match(r'(\s*\(model\s+")([^"]+)(".*)', line)
        if match:
            replacement_path = model_reference_paths[min(model_index, len(model_reference_paths) - 1)]
            updated_lines.append(
                f'{match.group(1)}{escape_kicad_string(replacement_path)}{match.group(3)}\n'
            )
            model_index += 1
        else:
            updated_lines.append(line)

    return "".join(updated_lines)


def copy_file(source: Path, destination: Path, overwrite: bool, collision_label: str) -> None:
    ensure_writable_path(destination, overwrite, collision_label)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def ensure_writable_path(destination: Path, overwrite: bool, collision_label: str) -> None:
    if destination.exists() and not overwrite:
        raise ImportErrorWithExitCode(
            f"{collision_label} already exists at {display_path(destination)}; use the matching overwrite flag to replace it",
            exit_code=4,
        )


def write_footprint(destination: Path, content: str, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        raise ImportErrorWithExitCode(
            f"footprint already exists at {display_path(destination)}; use --overwrite-footprint to replace it",
            exit_code=4,
        )
    destination.write_text(content, encoding="utf-8")


def validate_symbol_library_text(symbol_target: Path, content: str, verbose: bool) -> None:
    temp_path = TMP_ROOT / ".validate" / symbol_target.name
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT), str(temp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if verbose and result.stdout.strip():
        print("Validator stdout:")
        print(result.stdout.rstrip())
    if verbose and result.stderr.strip():
        print("Validator stderr:")
        print(result.stderr.rstrip())
    if result.returncode != 0:
        details = result.stdout.strip() or result.stderr.strip() or "validation failed"
        raise ImportErrorWithExitCode(details, exit_code=5)


def offer_setup_kicad(interactive: bool) -> None:
    if interactive:
        should_run = prompt_yes_no(
            "New libraries were created. Run scripts/setup-kicad.sh now?", default=True
        )
        if should_run:
            result = subprocess.run([str(SETUP_KICAD_SCRIPT)], cwd=REPO_ROOT, check=False)
            if result.returncode != 0:
                raise ImportErrorWithExitCode(
                    "scripts/setup-kicad.sh failed", exit_code=result.returncode or 1
                )
            return
    print("Run ./scripts/setup-kicad.sh to refresh KiCad library setup.")


def block_depth_delta(line: str) -> int:
    return line.count("(") - line.count(")")


def get_first_property_value(properties: list[PropertyBlock], name: str) -> str:
    for prop in properties:
        if prop.name == name:
            return prop.value
    return ""


def property_value_or_blank(property_block: PropertyBlock | None) -> str:
    return property_block.value if property_block is not None else ""


def slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "part"


def escape_kicad_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def model_reference_path(destination: Path) -> str:
    try:
        relative_to_model_root = destination.resolve().relative_to(MODEL_ROOT.resolve())
        return "${GS_3DMODEL_DIR}/" + relative_to_model_root.as_posix()
    except ValueError:
        return destination.resolve().as_posix()


def models_dir_state_value(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
