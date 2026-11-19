from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from kicad_lib_tools.categories import load_category_libraries
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
    remember_category_library,
    render_summary,
    resolve_footprint_link_choice,
    resolve_metadata_value,
    resolve_models_dir,
    stage_converter_output,
    state_bool,
    validate_plan,
)
from kicad_lib_tools.lcsc_api import LCSCPart
from kicad_lib_tools.symbols import PropertyBlock, SymbolBlock
from tests.fakes import ScriptedPrompter


def make_plan(**overrides: object) -> ImportPlan:
    plan = ImportPlan(
        lcsc_id="C2040",
        converter_command="easyeda2kicad",
        stage_name="c2040",
        part=None,
        import_symbol=True,
        import_3d=True,
        symbol_library="GS_IC",
        footprint_library="GS_SO",
        models_dir=Path("3d-models"),
        footprint_link=FootprintLinkChoice(mode="generated"),
        symbol_name="TPS5430DDAR",
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


USB_C_PART = LCSCPart(
    lcsc_id="C165948",
    manufacturer="Korean Hroparts Elec",
    mpn="TYPE-C-31-M-12",
    description="USB-C Receptacle Connector 16 Position Surface Mount",
    datasheet_url="",
    package="SMD",
    category="USB, DVI, HDMI Connector Assemblies",
    parent_category="Connectors",
)


def make_libraries(
    repo: LibraryConfig,
    symbols: list[str] | None = None,
    footprints: dict[str, list[str]] | None = None,
) -> None:
    for name in symbols or []:
        (repo.symbol_path / f"{name}.kicad_sym").write_text("(kicad_symbol_lib\n)\n", "utf-8")
    for name, footprint_names in (footprints or {}).items():
        library = repo.footprint_path / f"{name}.pretty"
        library.mkdir()
        for footprint in footprint_names:
            (library / f"{footprint}.kicad_mod").write_text(
                f'(footprint "{footprint}"\n)\n', "utf-8"
            )


def make_footprint_args(**overrides: object) -> argparse.Namespace:
    args = parse_args([])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_resolve_footprint_link_choice_defaults_to_generated_for_non_interactive_import() -> None:
    choice = resolve_footprint_link_choice(
        args=make_footprint_args(),
        state={"last_footprint_link_mode": "existing"},
        ui=None,
        import_symbol=True,
        symbol_library="GS_IC",
    )
    assert choice == FootprintLinkChoice(mode="generated")


def test_resolve_footprint_link_choice_no_footprint_flag_selects_none() -> None:
    choice = resolve_footprint_link_choice(
        args=make_footprint_args(no_footprint=True),
        state={"last_footprint_link_mode": "generated"},
        ui=None,
        import_symbol=True,
        symbol_library="GS_IC",
    )
    assert choice == FootprintLinkChoice(mode="none")


def test_resolve_footprint_link_choice_rejects_generated_with_no_footprint() -> None:
    with pytest.raises(ImportErrorWithExitCode, match="conflicts"):
        resolve_footprint_link_choice(
            args=make_footprint_args(footprint_link_mode="generated", no_footprint=True),
            state={},
            ui=None,
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
            ui=None,
            import_symbol=False,
            symbol_library=None,
        )


def test_resolve_footprint_link_choice_resolves_existing_repo_footprint(
    repo: LibraryConfig,
) -> None:
    make_libraries(repo, footprints={"GS_SO": ["SOT-23"]})
    choice = resolve_footprint_link_choice(
        args=make_footprint_args(
            footprint_link_mode="existing",
            existing_footprint_lib="GS_SO",
            existing_footprint="SOT-23",
        ),
        state={},
        ui=None,
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
    args = parse_args([])
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
        ui=None,
    )

    assert plan.mpn == "TPS5430DDAR"


def test_enrich_plan_with_metadata_falls_back_to_legacy_mfr_part_field() -> None:
    args = parse_args([])
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
        ui=None,
    )

    assert plan.mpn == "TPS5430DDAR"


def test_enrich_plan_with_metadata_reads_spice_warning_override() -> None:
    args = parse_args([])
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
        ui=None,
    )

    assert plan.spice_warning_override == "digital-only symbol"


def test_resolve_metadata_value_shows_skip_hint_for_optional_blank_fields() -> None:
    ui = ScriptedPrompter([""])
    assert (
        resolve_metadata_value(
            provided=None,
            prompt="Datasheet",
            default="",
            ui=ui,
            required=False,
        )
        == ""
    )
    assert [question.prompt for question in ui.questions] == ["Datasheet (leave blank to skip): "]


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
    assert resolve_models_dir("3d-models/custom", default="3d-models", ui=None) == (
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


def test_stage_converter_output_tolerates_missing_3d_directory(repo: LibraryConfig) -> None:

    def fake_run_converter(
        *,
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

    artifacts = stage_converter_output(make_plan(stage_name="c2158003"), fake_run_converter)

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

    offer_setup_kicad(ui=None)

    assert len(calls) == 1
    assert calls[0][0][-1] == str(repo.setup_script_path)
    assert calls[0][1] == repo.repo_root
    assert "KiCad library setup refreshed." in capsys.readouterr().out


def test_offer_setup_kicad_skips_setup_when_declined_interactively(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:

    def fail_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("setup-kicad.py should not run when declined")

    monkeypatch.setattr("kicad_lib_tools.importer.subprocess.run", fail_run)

    offer_setup_kicad(ui=ScriptedPrompter(["n"]))

    assert "Run ./scripts/setup-kicad.py to refresh KiCad library setup." in capsys.readouterr().out


def test_describe_part_shows_identity_description_and_category() -> None:
    assert describe_part(USB_C_PART) == (
        "C165948: Korean Hroparts Elec TYPE-C-31-M-12\n"
        "  USB-C Receptacle Connector 16 Position Surface Mount\n"
        "  Connectors > USB, DVI, HDMI Connector Assemblies, package SMD"
    )


def test_interactive_plan_defaults_to_symbol_library_and_3d_models(
    repo: LibraryConfig,
) -> None:
    make_libraries(
        repo,
        symbols=["GS_Acoustic", "GS_Connectors"],
        footprints={"GS_Acoustic": [], "GS_Connectors": ["JST_XH"]},
    )
    repo.category_file_path.write_text('"Connectors" = "GS_Connectors"\n', encoding="utf-8")
    state: dict[str, object] = {
        "last_import_3d": False,
        "last_footprint_link_mode": "existing",
        "last_symbol_lib": "GS_Acoustic",
        "last_existing_footprint_lib": "GS_Connectors",
    }
    ui = ScriptedPrompter(["", None, "generated", None, "", ""])

    plan = build_initial_plan(
        parse_args(["--lcsc-id", "C165948"]), state, ui=ui, lookup=lambda _lcsc_id: USB_C_PART
    )

    assert [(q.kind, q.prompt, q.default) for q in ui.questions] == [
        ("yes_no", "Import symbol", True),
        ("select", "Select symbol library", "GS_Connectors"),
        ("select", "Footprint", "existing"),
        ("select", "Select footprint library for the EasyEDA footprint", "GS_Connectors"),
        ("yes_no", "Import 3D models", True),
        ("text", "3D model directory [3d-models]: ", None),
    ]
    assert plan.footprint_link == FootprintLinkChoice(mode="generated")
    assert plan.footprint_library == "GS_Connectors"
    assert plan.import_3d


def test_interactive_plan_asks_before_reimporting_a_known_lcsc_id(repo: LibraryConfig) -> None:
    (repo.symbol_path / "GS_Connectors.kicad_sym").write_text(
        '(kicad_symbol_lib\n\t(symbol "USB_C"\n\t\t(property "LCSC ID" "C165948"\n\t\t)\n\t)\n)\n',
        encoding="utf-8",
    )
    ui = ScriptedPrompter([""])

    with pytest.raises(ImportErrorWithExitCode, match="import cancelled"):
        build_initial_plan(parse_args(["--lcsc-id", "C165948"]), {}, ui=ui, lookup=lambda _: None)

    assert ui.questions[0].prompt == "Import it again?"
    assert ui.questions[0].default is False


def test_remember_category_library_saves_new_categories(repo: LibraryConfig) -> None:
    remember_category_library(make_plan(part=USB_C_PART, symbol_library="GS_USB"))
    remember_category_library(make_plan(part=USB_C_PART, symbol_library="GS_Other"))
    remember_category_library(make_plan(part=None, symbol_library="GS_Other"))
    assert load_category_libraries(repo.category_file_path) == {
        "USB, DVI, HDMI Connector Assemblies": "GS_USB"
    }


def test_enrich_plan_suggests_sanitized_staged_symbol_name() -> None:
    artifacts = make_artifacts(
        symbol_block=SymbolBlock(name="IRM-V838M3-C/TR1", start=0, end=1, text=""),
    )
    ui = ScriptedPrompter(["", "", "", "IR receiver", "IRM-V838M3-C/TR1", "", "", ""])
    plan = enrich_plan_with_metadata(
        plan=make_plan(), args=parse_args([]), artifacts=artifacts, ui=ui
    )
    assert ui.questions[0].prompt == "Symbol name [IRM-V838M3-C_TR1]: "
    assert plan.symbol_name == "IRM-V838M3-C_TR1"
