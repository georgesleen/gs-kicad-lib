from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from kicad_lib_tools.cli import parse_args
from kicad_lib_tools.config import LibraryConfig
from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.importer import (
    FootprintLinkChoice,
    ImportPlan,
    StagedArtifacts,
    build_initial_plan,
    build_next_state,
    describe_part,
    enrich_plan_with_metadata,
    first_existing,
    normalize_lcsc_id,
    offer_setup_kicad,
    render_summary,
    resolve_footprint_link_choice,
    resolve_metadata_value,
    resolve_models_dir,
    stage_converter_output,
    state_bool,
    validate_plan,
)
from kicad_lib_tools.lcsc_api import LCSCPart
from kicad_lib_tools.selectors import SelectionOption
from kicad_lib_tools.symbols import PropertyBlock, SymbolBlock


def make_plan(**overrides: object) -> ImportPlan:
    plan = ImportPlan(
        lcsc_id="C2040",
        converter_command="easyeda2kicad",
        stage_name="c2040",
        import_symbol=True,
        import_3d=True,
        symbol_library="GS_IC",
        footprint_library="GS_SO",
        models_dir=Path("3d-models"),
        footprint_link=FootprintLinkChoice(mode="generated"),
        manufacturer="Texas Instruments",
        mpn="TPS5430DDAR",
        datasheet="https://example.invalid/ds.pdf",
        description="Buck regulator",
        package="SOIC-8",
        field_validation_override="",
        spice_warning_override="",
        overwrite_symbol=False,
        overwrite_footprint=False,
        overwrite_models=False,
        verbose=False,
    )
    for key, value in overrides.items():
        setattr(plan, key, value)
    return plan


def make_artifacts(**overrides: object) -> StagedArtifacts:
    artifacts = StagedArtifacts(
        stage_dir=Path("tmp/easyeda-import/c2040"),
        output_base=Path("tmp/easyeda-import/c2040/generated"),
        symbol_block=SymbolBlock(
            name="TPS5430DDAR", start=0, end=1, text='(symbol "TPS5430DDAR")\n'
        ),
        staged_symbol_path=Path("tmp/easyeda-import/c2040/generated.kicad_sym"),
        staged_properties=[
            PropertyBlock(
                name="Manufacturer",
                start=0,
                end=1,
                value="Texas Instruments",
                hidden=True,
            ),
        ],
        staged_footprint_path=Path("tmp/easyeda-import/c2040/generated.pretty/SOIC-8.kicad_mod"),
        staged_footprint_name="SOIC-8",
        staged_model_paths=[Path("tmp/easyeda-import/c2040/generated.step")],
        converter_result=subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    )
    for key, value in overrides.items():
        setattr(artifacts, key, value)
    return artifacts


def make_footprint_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "footprint_link_mode": None,
        "no_footprint": False,
        "existing_footprint_lib": None,
        "existing_footprint": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_resolve_footprint_link_choice_defaults_to_generated_for_non_interactive_import() -> None:
    choice = resolve_footprint_link_choice(
        args=make_footprint_args(),
        state={"last_footprint_link_mode": "existing"},
        interactive=False,
        import_symbol=True,
        symbol_library="GS_IC",
    )
    assert choice == FootprintLinkChoice(mode="generated")


def test_resolve_footprint_link_choice_no_footprint_flag_selects_none() -> None:
    choice = resolve_footprint_link_choice(
        args=make_footprint_args(no_footprint=True),
        state={"last_footprint_link_mode": "generated"},
        interactive=False,
        import_symbol=True,
        symbol_library="GS_IC",
    )
    assert choice == FootprintLinkChoice(mode="none")


def test_resolve_footprint_link_choice_rejects_generated_with_no_footprint() -> None:
    with pytest.raises(ImportErrorWithExitCode, match="conflicts"):
        resolve_footprint_link_choice(
            args=make_footprint_args(footprint_link_mode="generated", no_footprint=True),
            state={},
            interactive=False,
            import_symbol=True,
            symbol_library="GS_IC",
        )


def test_resolve_footprint_link_choice_rejects_existing_without_symbol() -> None:
    with pytest.raises(ImportErrorWithExitCode, match="requires a symbol"):
        resolve_footprint_link_choice(
            args=make_footprint_args(
                footprint_link_mode="existing",
                existing_footprint_lib="GS_SO",
                existing_footprint="SOT-23",
            ),
            state={},
            interactive=False,
            import_symbol=False,
            symbol_library=None,
        )


def test_resolve_footprint_link_choice_resolves_existing_repo_footprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kicad_lib_tools.importer.list_library_footprints", lambda _library: ["SOT-23"]
    )
    choice = resolve_footprint_link_choice(
        args=make_footprint_args(
            footprint_link_mode="existing",
            existing_footprint_lib="GS_SO",
            existing_footprint="SOT-23",
        ),
        state={},
        interactive=False,
        import_symbol=True,
        symbol_library="GS_IC",
    )
    assert choice == FootprintLinkChoice(
        mode="existing",
        existing_library="GS_SO",
        existing_footprint="SOT-23",
    )


def test_plan_imports_footprint_only_for_generated_mode() -> None:
    assert make_plan().import_footprint
    assert not make_plan(footprint_link=FootprintLinkChoice(mode="none")).import_footprint


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        (["GS_Connectors", "GS_SO"], "GS_Connectors"),
        (["GS_Optoelectronic", "GS_SO"], "GS_SO"),
        ([None, None], None),
    ],
)
def test_first_existing_skips_missing_libraries(
    candidates: list[str | None], expected: str | None
) -> None:
    assert first_existing(candidates, ["GS_Connectors", "GS_SO"]) == expected


def test_validate_plan_rejects_missing_symbol_metadata() -> None:
    plan = make_plan(manufacturer="", mpn="", description="", package="")
    with pytest.raises(
        ImportErrorWithExitCode,
        match=r"missing required symbol fields: Description, Manufacturer, MPN, Package",
    ):
        validate_plan(plan, make_artifacts())


def test_validate_plan_allows_missing_metadata_when_override_present() -> None:
    plan = make_plan(
        manufacturer="",
        mpn="",
        description="",
        package="",
        field_validation_override="prototype-only part",
    )
    validate_plan(plan, make_artifacts())


def test_enrich_plan_with_metadata_uses_staged_mpn_by_default() -> None:
    args = argparse.Namespace(
        manufacturer=None,
        datasheet=None,
        description=None,
        mpn=None,
        package=None,
        field_validation_override="",
        spice_warning_override=None,
    )
    artifacts = make_artifacts(
        staged_properties=[
            PropertyBlock(
                name="Manufacturer",
                start=0,
                end=1,
                value="Texas Instruments",
                hidden=True,
            ),
            PropertyBlock(name="Description", start=1, end=2, value="Buck regulator", hidden=True),
            PropertyBlock(
                name="Datasheet",
                start=2,
                end=3,
                value="https://example.invalid/ds.pdf",
                hidden=True,
            ),
            PropertyBlock(name="MPN", start=3, end=4, value="TPS5430DDAR", hidden=True),
        ]
    )

    plan = enrich_plan_with_metadata(
        plan=make_plan(manufacturer="", mpn="", datasheet="", description="", package=""),
        args=args,
        artifacts=artifacts,
        interactive=False,
    )

    assert plan.mpn == "TPS5430DDAR"


def test_enrich_plan_with_metadata_falls_back_to_legacy_mfr_part_field() -> None:
    args = argparse.Namespace(
        manufacturer=None,
        datasheet=None,
        description=None,
        mpn=None,
        package=None,
        field_validation_override="",
        spice_warning_override=None,
    )
    artifacts = make_artifacts(
        staged_properties=[
            PropertyBlock(
                name="Manufacturer",
                start=0,
                end=1,
                value="Texas Instruments",
                hidden=True,
            ),
            PropertyBlock(name="Description", start=1, end=2, value="Buck regulator", hidden=True),
            PropertyBlock(
                name="Datasheet",
                start=2,
                end=3,
                value="https://example.invalid/ds.pdf",
                hidden=True,
            ),
            PropertyBlock(name="Mfr. Part #", start=3, end=4, value="TPS5430DDAR", hidden=True),
        ]
    )

    plan = enrich_plan_with_metadata(
        plan=make_plan(manufacturer="", mpn="", datasheet="", description="", package=""),
        args=args,
        artifacts=artifacts,
        interactive=False,
    )

    assert plan.mpn == "TPS5430DDAR"


def test_enrich_plan_with_metadata_reads_spice_warning_override() -> None:
    args = argparse.Namespace(
        manufacturer=None,
        datasheet=None,
        description=None,
        mpn=None,
        package=None,
        field_validation_override="",
        spice_warning_override=None,
    )
    artifacts = make_artifacts(
        staged_properties=[
            PropertyBlock(
                name="Manufacturer",
                start=0,
                end=1,
                value="Texas Instruments",
                hidden=True,
            ),
            PropertyBlock(name="Description", start=1, end=2, value="Buck regulator", hidden=True),
            PropertyBlock(
                name="Datasheet",
                start=2,
                end=3,
                value="https://example.invalid/ds.pdf",
                hidden=True,
            ),
            PropertyBlock(name="MPN", start=3, end=4, value="TPS5430DDAR", hidden=True),
            PropertyBlock(
                name="SPICE Warning Override",
                start=4,
                end=5,
                value="digital-only symbol",
                hidden=True,
            ),
        ]
    )

    plan = enrich_plan_with_metadata(
        plan=make_plan(manufacturer="", mpn="", datasheet="", description="", package=""),
        args=args,
        artifacts=artifacts,
        interactive=False,
    )

    assert plan.spice_warning_override == "digital-only symbol"


def test_resolve_metadata_value_shows_skip_hint_for_optional_blank_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    def fake_prompt_text(prompt: str) -> str:
        prompts.append(prompt)
        return ""

    monkeypatch.setattr("kicad_lib_tools.importer.prompt_text", fake_prompt_text)

    assert (
        resolve_metadata_value(
            provided=None,
            prompt="Datasheet",
            default="",
            interactive=True,
            required=False,
        )
        == ""
    )
    assert prompts == ["Datasheet (leave blank to skip): "]


def test_render_summary_includes_creation_flags(repo: LibraryConfig) -> None:
    summary = render_summary(make_plan(models_dir=repo.model_path), make_artifacts())
    assert "will create symbol library: yes" in summary
    assert "will create footprint library: yes" in summary
    assert "staged models: 1" in summary


def test_build_next_state_persists_previous_choices() -> None:
    plan = make_plan(
        models_dir=Path.cwd() / "3d-models" / "custom",
        footprint_link=FootprintLinkChoice(
            mode="existing",
            existing_library="GS_SO",
            existing_footprint="SOT-23",
        ),
    )
    state = build_next_state(plan)
    assert state["last_symbol_lib"] == "GS_IC"
    assert state["last_footprint_lib"] == "GS_SO"
    assert state["last_existing_footprint_lib"] == "GS_SO"
    assert state["last_existing_footprint_name"] == "SOT-23"
    assert state["last_footprint_link_mode"] == "existing"


def test_resolve_models_dir_resolves_repo_relative_paths(repo: LibraryConfig) -> None:
    assert resolve_models_dir("3d-models/custom", default="3d-models", interactive=False) == (
        repo.repo_root / "3d-models" / "custom"
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("C2040", "C2040"), (" c2040 ", "C2040")],
)
def test_normalize_lcsc_id_accepts_expected_format(raw_value: str, expected: str) -> None:
    assert normalize_lcsc_id(raw_value) == expected


def test_normalize_lcsc_id_rejects_invalid_prefix() -> None:
    with pytest.raises(ImportErrorWithExitCode, match="Invalid LCSC ID"):
        normalize_lcsc_id("2040")


@pytest.mark.parametrize(
    ("raw_value", "default", "expected"),
    [
        (True, False, True),
        ("yes", False, True),
        ("0", True, False),
        ("unknown", True, True),
        (None, False, False),
    ],
)
def test_state_bool_handles_bool_and_string_values(
    raw_value: object, default: bool, expected: bool
) -> None:
    state = {} if raw_value is None else {"flag": raw_value}
    assert state_bool(state, "flag", default) is expected


def test_stage_converter_output_tolerates_missing_3d_directory(
    repo: LibraryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def fake_run_converter(
        converter_command: str,
        lcsc_id: str,
        output_base: Path,
        verbose: bool,
    ) -> subprocess.CompletedProcess[str]:
        output_base.parent.mkdir(parents=True, exist_ok=True)
        output_base.with_suffix(".kicad_sym").write_text(
            """\
(kicad_symbol_lib
  (symbol "TPS5430DDAR"
    (property "Reference" "U" (id 0) (at 0 0 0) (effects (font (size 1.27 1.27))))
  )
)
""",
            encoding="utf-8",
        )
        footprint_dir = output_base.with_suffix(".pretty")
        footprint_dir.mkdir()
        (footprint_dir / "SOIC-8.kicad_mod").write_text(
            '(footprint "GS_SO:SOIC-8"\n)\n',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("kicad_lib_tools.importer.run_converter", fake_run_converter)

    artifacts = stage_converter_output(make_plan(stage_name="c2158003"))

    assert artifacts.staged_footprint_name == "SOIC-8"
    assert artifacts.staged_model_paths == []


def test_offer_setup_kicad_runs_setup_script_non_interactive(
    repo: LibraryConfig,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[list[str], Path, bool]] = []

    def fake_run(args: list[str], cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd, check))
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("kicad_lib_tools.importer.subprocess.run", fake_run)

    offer_setup_kicad(interactive=False)

    assert len(calls) == 1
    assert calls[0][0][-1] == str(repo.setup_script_path)
    assert calls[0][1] == repo.repo_root
    assert "KiCad library setup refreshed." in capsys.readouterr().out


def test_offer_setup_kicad_skips_setup_when_declined_interactively(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("kicad_lib_tools.importer.prompt_yes_no", lambda prompt, default: False)

    def fail_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("setup-kicad.py should not run when declined")

    monkeypatch.setattr("kicad_lib_tools.importer.subprocess.run", fail_run)

    offer_setup_kicad(interactive=True)

    assert "Run ./scripts/setup-kicad.py to refresh KiCad library setup." in capsys.readouterr().out


def test_describe_part_shows_identity_description_and_category() -> None:
    part = LCSCPart(
        lcsc_id="C165948",
        manufacturer="Korean Hroparts Elec",
        mpn="TYPE-C-31-M-12",
        description="USB-C Receptacle Connector 16 Position Surface Mount",
        datasheet_url="",
        package="SMD",
        category="USB, DVI, HDMI Connector Assemblies",
        parent_category="Connectors",
    )
    assert describe_part(part) == (
        "C165948: Korean Hroparts Elec TYPE-C-31-M-12\n"
        "  USB-C Receptacle Connector 16 Position Surface Mount\n"
        "  Connectors > USB, DVI, HDMI Connector Assemblies, package SMD"
    )


def test_interactive_plan_defaults_to_symbol_library_and_3d_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menus: list[tuple[str, str | None]] = []

    def fake_select_one(
        *,
        title: str,
        options: list[SelectionOption],
        default_value: str | None = None,
        preview: object = None,
    ) -> SelectionOption:
        menus.append((title, default_value))
        values = {option.value: option for option in options}
        return values["generated"] if "generated" in values else values[str(default_value)]

    monkeypatch.setattr("kicad_lib_tools.importer.select_one", fake_select_one)
    monkeypatch.setattr("kicad_lib_tools.interaction.prompt_text", lambda _prompt: "")
    monkeypatch.setattr("kicad_lib_tools.importer.prompt_text", lambda _prompt: "")
    monkeypatch.setattr("kicad_lib_tools.importer.lookup_part", lambda _lcsc_id: None)
    monkeypatch.setattr("kicad_lib_tools.importer.confirm_not_duplicate", lambda _lcsc_id: None)
    monkeypatch.setattr(
        "kicad_lib_tools.importer.list_footprint_libraries",
        lambda: ["GS_Acoustic", "GS_Connectors"],
    )
    monkeypatch.setattr(
        "kicad_lib_tools.importer.list_symbol_libraries",
        lambda: ["GS_Acoustic", "GS_Connectors"],
    )
    state: dict[str, object] = {
        "last_import_3d": False,
        "last_footprint_link_mode": "existing",
        "last_symbol_lib": "GS_Connectors",
        "last_existing_footprint_lib": "GS_Connectors",
    }

    plan = build_initial_plan(parse_args(["--lcsc-id", "C165948"]), state, interactive=True)

    assert menus == [
        ("Select symbol library", "GS_Connectors"),
        ("Footprint", "existing"),
        ("Select footprint library for the EasyEDA footprint", "GS_Connectors"),
    ]
    assert plan.footprint_link == FootprintLinkChoice(mode="generated")
    assert plan.footprint_library == "GS_Connectors"
    assert plan.import_3d
