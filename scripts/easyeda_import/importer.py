from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
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
    create_footprint_library,
    create_symbol_library,
    list_footprint_libraries,
    list_library_footprints,
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
from .selectors import SelectionOption, options_from_values, select_one
from .state import load_state, save_state
from .symbols import (
    PropertyBlock,
    SymbolBlock,
    extract_single_symbol,
    get_first_property_value,
    parse_symbol_properties,
    prepare_symbol_block,
    property_value_or_blank,
    render_symbol_library_update,
    validate_symbol_library_text,
)


@dataclass
class FootprintLinkChoice:
    mode: str
    existing_library: str | None = None
    existing_footprint: str | None = None

    def reference(
        self, generated_library: str | None, generated_footprint: str | None
    ) -> str:
        # Repo-specific mapping stays here. The converter only stages a generated
        # footprint; linking to an existing repo footprint is handled entirely by
        # the wrapper after staging.
        if self.mode == "generated":
            if not generated_library or not generated_footprint:
                raise ImportErrorWithExitCode(
                    "generated footprint link requested without an imported footprint",
                    exit_code=1,
                )
            return f"{generated_library}:{generated_footprint}"
        if self.mode == "existing":
            if not self.existing_library or not self.existing_footprint:
                raise ImportErrorWithExitCode(
                    "existing footprint link requested without a selected footprint",
                    exit_code=1,
                )
            return f"{self.existing_library}:{self.existing_footprint}"
        return ""


@dataclass
class ImportPlan:
    lcsc_id: str
    converter_command: str
    stage_name: str
    import_symbol: bool
    import_footprint: bool
    import_3d: bool
    symbol_library: str | None
    footprint_library: str | None
    models_dir: Path | None
    footprint_link: FootprintLinkChoice
    manufacturer: str
    mpn: str
    datasheet: str
    description: str
    package: str
    field_validation_override: str
    spice_warning_override: str
    overwrite_symbol: bool
    overwrite_footprint: bool
    overwrite_models: bool
    verbose: bool


@dataclass
class StagedArtifacts:
    stage_dir: Path
    output_base: Path
    symbol_block: SymbolBlock
    staged_symbol_path: Path
    staged_properties: list[PropertyBlock]
    staged_footprint_path: Path | None
    staged_footprint_name: str | None
    staged_model_paths: list[Path]
    converter_result: subprocess.CompletedProcess[str]


def run_import(args: argparse.Namespace) -> None:
    state = load_state()
    interactive = not args.non_interactive and sys.stdin.isatty() and sys.stdout.isatty()

    plan = build_initial_plan(args=args, state=state, interactive=interactive)
    artifacts = stage_converter_output(plan)
    plan = enrich_plan_with_metadata(
        plan=plan,
        args=args,
        artifacts=artifacts,
        interactive=interactive,
    )
    validate_plan(plan=plan, artifacts=artifacts)

    summary = render_summary(plan=plan, artifacts=artifacts)
    if interactive:
        print(summary)
        if not prompt_yes_no("Proceed with this import?", default=True):
            raise ImportErrorWithExitCode("import cancelled", exit_code=1)

    apply_import_plan(plan=plan, artifacts=artifacts, interactive=interactive)
    save_state(build_next_state(plan=plan))
    if interactive:
        print("Import completed.")
    else:
        print(summary)


def build_initial_plan(
    args: argparse.Namespace, state: dict[str, str], interactive: bool
) -> ImportPlan:
    default_import_symbol = state_bool(state, "last_import_symbol", True) if interactive else True
    default_import_footprint = (
        state_bool(state, "last_import_footprint", True) if interactive else True
    )
    default_import_3d = state_bool(state, "last_import_3d", True) if interactive else True

    converter_command = resolve_converter_command(args.converter_command)
    lcsc_id = normalize_lcsc_id(
        resolve_text_value(
            args.lcsc_id,
            prompt="LCSC ID",
            interactive=interactive,
            allow_blank=False,
        )
    )
    import_symbol = resolve_import_flag(
        explicit=not args.no_symbol if args.no_symbol else None,
        interactive=interactive,
        prompt="Import symbol",
        default=default_import_symbol,
    )
    import_footprint = resolve_import_flag(
        explicit=not args.no_footprint if args.no_footprint else None,
        interactive=interactive,
        prompt="Import generated footprint",
        default=default_import_footprint,
    )
    import_3d = resolve_import_flag(
        explicit=not args.no_3d if args.no_3d else None,
        interactive=interactive,
        prompt="Import 3D models",
        default=default_import_3d,
    )

    if not any([import_symbol, import_footprint, import_3d]):
        raise ImportErrorWithExitCode(
            "at least one of symbol, footprint, or 3D import must be enabled",
            exit_code=1,
        )

    symbol_library = (
        resolve_library_choice(
            provided=args.symbol_lib,
            prompt_title="Select symbol library",
            existing=list_symbol_libraries(),
            default=state.get("last_symbol_lib"),
            interactive=interactive,
            create_label="Create new symbol library...",
        )
        if import_symbol
        else None
    )
    footprint_library = (
        resolve_library_choice(
            provided=args.footprint_lib,
            prompt_title="Select generated footprint library",
            existing=list_footprint_libraries(),
            default=state.get("last_footprint_lib"),
            interactive=interactive,
            create_label="Create new footprint library...",
        )
        if import_footprint
        else None
    )
    models_dir = (
        resolve_models_dir(
            provided=args.models_dir,
            default=state.get("last_models_dir", str(MODEL_ROOT.relative_to(REPO_ROOT))),
            interactive=interactive,
        )
        if import_3d
        else None
    )

    footprint_link = resolve_footprint_link_choice(
        args=args,
        state=state,
        interactive=interactive,
        import_symbol=import_symbol,
        import_footprint=import_footprint,
    )

    return ImportPlan(
        lcsc_id=lcsc_id,
        converter_command=converter_command,
        stage_name=args.name or slugify(lcsc_id),
        import_symbol=import_symbol,
        import_footprint=import_footprint,
        import_3d=import_3d,
        symbol_library=symbol_library,
        footprint_library=footprint_library,
        models_dir=models_dir,
        footprint_link=footprint_link,
        manufacturer="",
        mpn="",
        datasheet="",
        description="",
        package="",
        field_validation_override="",
        spice_warning_override="",
        overwrite_symbol=args.overwrite_symbol,
        overwrite_footprint=args.overwrite_footprint,
        overwrite_models=args.overwrite_models,
        verbose=args.verbose,
    )


def stage_converter_output(plan: ImportPlan) -> StagedArtifacts:
    stage_dir = TMP_ROOT / plan.stage_name
    output_base = stage_dir / "generated"
    reset_stage_dir(stage_dir)
    converter_result = run_converter(
        converter_command=plan.converter_command,
        lcsc_id=plan.lcsc_id,
        output_base=output_base,
        verbose=plan.verbose,
    )

    staged_symbol_path = output_base.with_suffix(".kicad_sym")
    staged_footprint_dir = output_base.with_suffix(".pretty")
    staged_model_dir = output_base.with_suffix(".3dshapes")

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

    footprint_files = sorted(staged_footprint_dir.glob("*.kicad_mod"))
    if len(footprint_files) != 1:
        raise ImportErrorWithExitCode(
            f"expected exactly one staged footprint, found {len(footprint_files)}",
            exit_code=3,
        )
    staged_footprint_path = footprint_files[0]
    staged_footprint_name = parse_footprint_name(staged_footprint_path)
    staged_model_paths = (
        sorted(
            path
            for path in staged_model_dir.iterdir()
            if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS
        )
        if staged_model_dir.is_dir()
        else []
    )

    return StagedArtifacts(
        stage_dir=stage_dir,
        output_base=output_base,
        symbol_block=symbol_block,
        staged_symbol_path=staged_symbol_path,
        staged_properties=staged_properties,
        staged_footprint_path=staged_footprint_path,
        staged_footprint_name=staged_footprint_name,
        staged_model_paths=staged_model_paths,
        converter_result=converter_result,
    )


def enrich_plan_with_metadata(
    *,
    plan: ImportPlan,
    args: argparse.Namespace,
    artifacts: StagedArtifacts,
    interactive: bool,
) -> ImportPlan:
    if not plan.import_symbol:
        return plan

    staged_property_map = {prop.name: prop for prop in artifacts.staged_properties}
    manufacturer = resolve_metadata_value(
        provided=args.manufacturer,
        prompt="Manufacturer",
        default=get_first_property_value(artifacts.staged_properties, "Manufacturer"),
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
    description = resolve_metadata_value(
        provided=args.description,
        prompt="Description",
        default=property_value_or_blank(staged_property_map.get("Description")),
        interactive=interactive,
        required=not args.field_validation_override,
    )
    mpn = resolve_metadata_value(
        provided=args.mpn,
        prompt="MPN",
        default=property_value_or_blank(staged_property_map.get("MPN"))
        or property_value_or_blank(staged_property_map.get("Mfr. Part #")),
        interactive=interactive,
        required=not args.field_validation_override,
    )
    package = resolve_metadata_value(
        provided=args.package,
        prompt="Package",
        default=artifacts.staged_footprint_name or "",
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
    spice_warning_override = resolve_metadata_value(
        provided=args.spice_warning_override,
        prompt="SPICE Warning Override reason",
        default=property_value_or_blank(staged_property_map.get("SPICE Warning Override")),
        interactive=interactive,
        required=False,
    )
    plan.manufacturer = manufacturer
    plan.datasheet = datasheet
    plan.description = description
    plan.mpn = mpn
    plan.package = package
    plan.field_validation_override = validation_override
    plan.spice_warning_override = spice_warning_override
    return plan


def validate_plan(plan: ImportPlan, artifacts: StagedArtifacts) -> None:
    if plan.import_symbol and not plan.symbol_library:
        raise ImportErrorWithExitCode("symbol import requires a target symbol library")
    if plan.import_footprint and not plan.footprint_library:
        raise ImportErrorWithExitCode(
            "generated footprint import requires a target footprint library"
        )
    if plan.import_3d and plan.models_dir is None:
        raise ImportErrorWithExitCode("3D import requires a models directory")

    if plan.import_symbol:
        if plan.footprint_link.mode == "generated" and not plan.import_footprint:
            raise ImportErrorWithExitCode(
                "generated footprint linking requires generated footprint import",
                exit_code=1,
            )
        if plan.footprint_link.mode == "existing":
            if (
                not plan.footprint_link.existing_library
                or not plan.footprint_link.existing_footprint
            ):
                raise ImportErrorWithExitCode(
                    "existing footprint linking requires both library and footprint",
                    exit_code=1,
                )
        if not plan.field_validation_override:
            missing = [
                name
                for name, value in {
                    "Description": plan.description,
                    "Manufacturer": plan.manufacturer,
                    "MPN": plan.mpn,
                    "Package": plan.package,
                }.items()
                if not value
            ]
            if missing:
                raise ImportErrorWithExitCode(
                    "missing required symbol fields: " + ", ".join(missing),
                    exit_code=1,
                )

    if plan.footprint_link.mode == "generated" and not artifacts.staged_footprint_name:
        raise ImportErrorWithExitCode("staged footprint data is missing", exit_code=3)


def apply_import_plan(
    *, plan: ImportPlan, artifacts: StagedArtifacts, interactive: bool
) -> None:
    created_symbol_lib = False
    created_footprint_lib = False

    symbol_target = (
        SYMBOL_DIR / f"{plan.symbol_library}.kicad_sym" if plan.symbol_library else None
    )
    footprint_dir = (
        FOOTPRINT_DIR / f"{plan.footprint_library}.pretty"
        if plan.footprint_library
        else None
    )

    if plan.import_symbol and symbol_target is not None and not symbol_target.exists():
        create_symbol_library(symbol_target)
        created_symbol_lib = True
    if plan.import_footprint and footprint_dir is not None and not footprint_dir.exists():
        create_footprint_library(footprint_dir)
        created_footprint_lib = True
    if plan.import_3d and plan.models_dir is not None:
        plan.models_dir.mkdir(parents=True, exist_ok=True)

    imported_models: list[tuple[Path, str]] = []
    if plan.import_3d and plan.models_dir is not None:
        for staged_model in artifacts.staged_model_paths:
            destination = plan.models_dir / staged_model.name
            ensure_writable_path(
                destination=destination,
                overwrite=plan.overwrite_models,
                collision_label=f"3D model {staged_model.name}",
            )
        for staged_model in artifacts.staged_model_paths:
            destination = plan.models_dir / staged_model.name
            copy_file(
                source=staged_model,
                destination=destination,
                overwrite=plan.overwrite_models,
                collision_label=f"3D model {staged_model.name}",
            )
            imported_models.append((destination, model_reference_path(destination)))

    if plan.import_footprint and footprint_dir is not None and artifacts.staged_footprint_path:
        footprint_destination = footprint_dir / artifacts.staged_footprint_path.name
        ensure_writable_path(
            destination=footprint_destination,
            overwrite=plan.overwrite_footprint,
            collision_label="footprint",
        )
        footprint_text = artifacts.staged_footprint_path.read_text(encoding="utf-8")
        footprint_text = rewrite_model_paths(
            footprint_text=footprint_text,
            model_reference_paths=[reference for _dest, reference in imported_models],
        )
        write_footprint(
            destination=footprint_destination,
            content=footprint_text,
            overwrite=plan.overwrite_footprint,
        )

    if plan.import_symbol and symbol_target is not None:
        prepared_symbol = prepare_symbol_block(
            symbol_block=artifacts.symbol_block.text,
            footprint_ref=plan.footprint_link.reference(
                generated_library=plan.footprint_library,
                generated_footprint=artifacts.staged_footprint_name,
            ),
            datasheet=plan.datasheet or "~",
            description=plan.description,
            manufacturer=plan.manufacturer,
            mpn=plan.mpn,
            lcsc_id=plan.lcsc_id,
            package=plan.package,
            validation_override=plan.field_validation_override,
            spice_warning_override=plan.spice_warning_override,
        )
        rendered_symbol_library = render_symbol_library_update(
            symbol_library_path=symbol_target,
            symbol_name=artifacts.symbol_block.name,
            symbol_block=prepared_symbol,
            overwrite=plan.overwrite_symbol,
        )
        validate_symbol_library_text(
            symbol_target=symbol_target,
            content=rendered_symbol_library,
            verbose=plan.verbose,
        )
        symbol_target.write_text(rendered_symbol_library, encoding="utf-8")

    if created_symbol_lib or created_footprint_lib:
        offer_setup_kicad(interactive=interactive)


def render_summary(plan: ImportPlan, artifacts: StagedArtifacts) -> str:
    lines = [
        "Import summary:",
        f"  LCSC ID: {plan.lcsc_id}",
        f"  converter: {plan.converter_command}",
        f"  symbol import: {'yes' if plan.import_symbol else 'no'}",
        f"  generated footprint import: {'yes' if plan.import_footprint else 'no'}",
        f"  3D model import: {'yes' if plan.import_3d else 'no'}",
    ]

    if plan.import_symbol:
        lines.append(f"  symbol library: {plan.symbol_library}")
        lines.append(f"  footprint link: {describe_footprint_link(plan.footprint_link)}")
        lines.append(f"  manufacturer: {plan.manufacturer or '~'}")
        lines.append(f"  mpn: {plan.mpn or '~'}")
        lines.append(f"  datasheet: {plan.datasheet or '~'}")
        lines.append(f"  description: {plan.description or '~'}")
        lines.append(f"  package: {plan.package or '~'}")
        lines.append(
            f"  field override: {plan.field_validation_override or 'none'}"
        )
        lines.append(
            f"  spice warning override: {plan.spice_warning_override or 'none'}"
        )
        lines.append(
            f"  will create symbol library: {'yes' if not (SYMBOL_DIR / f'{plan.symbol_library}.kicad_sym').exists() else 'no'}"
        )
    if plan.import_footprint and plan.footprint_library:
        lines.append(f"  generated footprint library: {plan.footprint_library}")
        lines.append(
            f"  will create footprint library: {'yes' if not (FOOTPRINT_DIR / f'{plan.footprint_library}.pretty').exists() else 'no'}"
        )
    if plan.import_3d and plan.models_dir is not None:
        lines.append(f"  3D model destination: {display_path(plan.models_dir)}")
    else:
        lines.append("  3D model destination: skip")

    lines.extend(
        [
            f"  overwrite symbol: {'yes' if plan.overwrite_symbol else 'no'}",
            f"  overwrite footprint: {'yes' if plan.overwrite_footprint else 'no'}",
            f"  overwrite 3D models: {'yes' if plan.overwrite_models else 'no'}",
            f"  staged symbol: {artifacts.symbol_block.name}",
            f"  staged footprint: {artifacts.staged_footprint_name or 'none'}",
            f"  staged models: {len(artifacts.staged_model_paths)}",
            f"  staging directory: {display_path(artifacts.stage_dir)}",
        ]
    )
    return "\n".join(lines)


def build_next_state(plan: ImportPlan) -> dict[str, str | bool]:
    state: dict[str, str | bool] = {
        "last_import_symbol": plan.import_symbol,
        "last_import_footprint": plan.import_footprint,
        "last_import_3d": plan.import_3d,
        "last_footprint_link_mode": plan.footprint_link.mode,
    }
    if plan.symbol_library:
        state["last_symbol_lib"] = plan.symbol_library
    if plan.footprint_library:
        state["last_footprint_lib"] = plan.footprint_library
    if plan.models_dir is not None:
        state["last_models_dir"] = models_dir_state_value(plan.models_dir)
    if plan.footprint_link.existing_library:
        state["last_existing_footprint_lib"] = plan.footprint_link.existing_library
    if plan.footprint_link.existing_footprint:
        state["last_existing_footprint_name"] = plan.footprint_link.existing_footprint
    return state


def describe_footprint_link(choice: FootprintLinkChoice) -> str:
    if choice.mode == "generated":
        return "generated footprint"
    if choice.mode == "existing":
        return f"existing {choice.existing_library}:{choice.existing_footprint}"
    return "none"


def resolve_import_flag(
    *,
    explicit: bool | None,
    interactive: bool,
    prompt: str,
    default: bool,
) -> bool:
    if explicit is not None:
        return explicit
    if not interactive:
        return default
    return prompt_yes_no(prompt, default=default)


def resolve_footprint_link_choice(
    *,
    args: argparse.Namespace,
    state: dict[str, str],
    interactive: bool,
    import_symbol: bool,
    import_footprint: bool,
) -> FootprintLinkChoice:
    if not import_symbol:
        return FootprintLinkChoice(mode="none")

    default_mode = state.get("last_footprint_link_mode", "generated")
    if not import_footprint and default_mode == "generated":
        default_mode = "none"

    if args.footprint_link_mode is not None:
        mode = args.footprint_link_mode
    elif interactive:
        options = [SelectionOption("existing", "Link to existing repo footprint")]
        if import_footprint:
            options.insert(0, SelectionOption("generated", "Link to generated footprint"))
        options.append(SelectionOption("none", "Leave symbol footprint link empty"))
        mode = select_one(
            title="Choose how the imported symbol should link its footprint",
            options=options,
            default_value=default_mode,
        ).value
    else:
        mode = "generated" if import_footprint else "none"

    if mode == "existing":
        library = resolve_existing_footprint_library(
            provided=args.existing_footprint_lib,
            default=state.get("last_existing_footprint_lib"),
            interactive=interactive,
        )
        footprint = resolve_existing_footprint_name(
            library=library,
            provided=args.existing_footprint,
            default=state.get("last_existing_footprint_name"),
            interactive=interactive,
        )
        return FootprintLinkChoice(
            mode=mode,
            existing_library=library,
            existing_footprint=footprint,
        )

    return FootprintLinkChoice(mode=mode)


def resolve_existing_footprint_library(
    *, provided: str | None, default: str | None, interactive: bool
) -> str:
    if provided:
        return normalize_library_name(provided)
    if not interactive:
        raise ImportErrorWithExitCode(
            "--existing-footprint-lib is required for existing footprint linking",
            exit_code=1,
        )
    options = options_from_values(list_footprint_libraries())
    return select_one(
        title="Select existing footprint library",
        options=options,
        default_value=default,
    ).value


def resolve_existing_footprint_name(
    *,
    library: str,
    provided: str | None,
    default: str | None,
    interactive: bool,
) -> str:
    existing_footprints = list_library_footprints(library)
    if provided:
        if provided not in existing_footprints:
            raise ImportErrorWithExitCode(
                f"existing footprint {provided} not found in {library}",
                exit_code=1,
            )
        return provided
    if not interactive:
        raise ImportErrorWithExitCode(
            "--existing-footprint is required for existing footprint linking",
            exit_code=1,
        )
    options = options_from_values(existing_footprints)
    return select_one(
        title=f"Select existing footprint in {library}",
        options=options,
        default_value=default if default in existing_footprints else None,
    ).value


def resolve_library_choice(
    *,
    provided: str | None,
    prompt_title: str,
    existing: list[str],
    default: str | None,
    interactive: bool,
    create_label: str,
) -> str:
    if provided:
        return normalize_library_name(provided)
    if not interactive:
        raise ImportErrorWithExitCode(
            f"missing required selection for {prompt_title.lower()}",
            exit_code=1,
        )
    options = options_from_values(existing)
    options.append(SelectionOption("__create__", create_label))
    selected = select_one(
        title=prompt_title,
        options=options,
        default_value=default if default in existing else None,
    )
    if selected.value != "__create__":
        return selected.value
    while True:
        candidate = prompt_text("New library name (GS_<Category>): ").strip()
        try:
            return normalize_library_name(candidate)
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


def normalize_lcsc_id(raw_value: str) -> str:
    value = raw_value.strip().upper()
    if not value.startswith("C"):
        raise ImportErrorWithExitCode("LCSC ID must start with C", exit_code=1)
    return value


def reset_stage_dir(stage_dir: Path) -> None:
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)


def offer_setup_kicad(interactive: bool) -> None:
    if interactive:
        should_run = prompt_yes_no(
            "New libraries were created. Run scripts/setup-kicad.sh now?", default=True
        )
        if not should_run:
            print("Run ./scripts/setup-kicad.sh to refresh KiCad library setup.")
            return

    result = subprocess.run([str(SETUP_KICAD_SCRIPT)], cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        raise ImportErrorWithExitCode(
            "scripts/setup-kicad.sh failed", exit_code=result.returncode or 1
        )
    print("KiCad library setup refreshed. Restart KiCad if new libraries do not appear immediately.")


def state_bool(state: dict[str, str], key: str, default: bool) -> bool:
    value = state.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if str(value).lower() in {"true", "1", "yes"}:
        return True
    if str(value).lower() in {"false", "0", "no"}:
        return False
    return default
