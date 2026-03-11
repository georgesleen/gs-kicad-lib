from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .converter import resolve_converter_command, run_converter
from .errors import ImportErrorWithExitCode
from .footprints import (
    copy_file,
    ensure_writable_path,
    parse_footprint_name,
    rewrite_model_paths,
    write_footprint,
)
from .interaction import prompt_text, prompt_yes_no
from .libraries import (
    ensure_footprint_library,
    ensure_symbol_library,
    list_footprint_libraries,
    list_symbol_libraries,
    normalize_library_name,
)
from .paths import (
    FOOTPRINT_DIR,
    MODEL_EXTENSIONS,
    MODEL_ROOT,
    REPO_ROOT,
    SETUP_KICAD_SCRIPT,
    SYMBOL_DIR,
    TMP_ROOT,
    display_path,
    model_reference_path,
    models_dir_state_value,
    slugify,
)
from .state import load_state, save_state
from .symbols import (
    extract_single_symbol,
    get_first_property_value,
    parse_symbol_properties,
    prepare_symbol_block,
    property_value_or_blank,
    render_symbol_library_update,
    validate_symbol_library_text,
)


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
    print(f"  symbol: {display_path(symbol_target)}")
    print(f"  footprint: {display_path(footprint_destination)}")
    if imported_models:
        print("  models:")
        for destination, _reference in imported_models:
            print(f"    {display_path(destination)}")
    else:
        print("  models: none")
    print(f"  staging: {display_path(stage_dir)}")
    if args.verbose and converter_result.stdout.strip():
        print("Converter stdout:")
        print(converter_result.stdout.rstrip())
    if args.verbose and converter_result.stderr.strip():
        print("Converter stderr:")
        print(converter_result.stderr.rstrip())

    if created_symbol_lib or created_footprint_lib:
        offer_setup_kicad(interactive=interactive)


def normalize_lcsc_id(raw_value: str) -> str:
    value = raw_value.strip().upper()
    if not value.startswith("C"):
        raise ImportErrorWithExitCode("LCSC ID must start with C", exit_code=1)
    return value


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


def reset_stage_dir(stage_dir: Path) -> None:
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)


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

