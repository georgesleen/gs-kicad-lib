from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from scripts.easyeda_import.errors import ImportErrorWithExitCode
from scripts.easyeda_import.importer import (
    FootprintLinkChoice,
    ImportPlan,
    StagedArtifacts,
    build_next_state,
    enrich_plan_with_metadata,
    normalize_lcsc_id,
    offer_setup_kicad,
    render_summary,
    resolve_footprint_link_choice,
    resolve_models_dir,
    stage_converter_output,
    state_bool,
    validate_plan,
)
from scripts.easyeda_import.symbols import PropertyBlock, SymbolBlock


def make_plan(**overrides: object) -> ImportPlan:
    plan = ImportPlan(
        lcsc_id="C2040",
        converter_command="easyeda2kicad",
        stage_name="c2040",
        import_symbol=True,
        import_footprint=True,
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
        symbol_block=SymbolBlock(name="TPS5430DDAR", start=0, end=1, text='(symbol "TPS5430DDAR")\n'),
        staged_symbol_path=Path("tmp/easyeda-import/c2040/generated.kicad_sym"),
        staged_properties=[
            PropertyBlock(name="Manufacturer", start=0, end=1, value="Texas Instruments", hidden=True),
        ],
        staged_footprint_path=Path("tmp/easyeda-import/c2040/generated.pretty/SOIC-8.kicad_mod"),
        staged_footprint_name="SOIC-8",
        staged_model_paths=[Path("tmp/easyeda-import/c2040/generated.step")],
        converter_result=subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
    )
    for key, value in overrides.items():
        setattr(artifacts, key, value)
    return artifacts


def test_resolve_footprint_link_choice_defaults_to_generated_for_non_interactive_import() -> None:
    args = argparse.Namespace(
        footprint_link_mode=None,
        existing_footprint_lib=None,
        existing_footprint=None,
    )
    choice = resolve_footprint_link_choice(
        args=args,
        state={},
        interactive=False,
        import_symbol=True,
        import_footprint=True,
    )
    assert choice == FootprintLinkChoice(mode="generated")


def test_resolve_footprint_link_choice_defaults_to_none_without_generated_footprint() -> None:
    args = argparse.Namespace(
        footprint_link_mode=None,
        existing_footprint_lib=None,
        existing_footprint=None,
    )
    choice = resolve_footprint_link_choice(
        args=args,
        state={"last_footprint_link_mode": "generated"},
        interactive=False,
        import_symbol=True,
        import_footprint=False,
    )
    assert choice == FootprintLinkChoice(mode="none")


def test_resolve_footprint_link_choice_resolves_existing_repo_footprint() -> None:
    args = argparse.Namespace(
        footprint_link_mode="existing",
        existing_footprint_lib="GS_SO",
        existing_footprint="SOT-23",
    )
    choice = resolve_footprint_link_choice(
        args=args,
        state={},
        interactive=False,
        import_symbol=True,
        import_footprint=False,
    )
    assert choice == FootprintLinkChoice(
        mode="existing",
        existing_library="GS_SO",
        existing_footprint="SOT-23",
    )


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
            PropertyBlock(name="Manufacturer", start=0, end=1, value="Texas Instruments", hidden=True),
            PropertyBlock(name="Description", start=1, end=2, value="Buck regulator", hidden=True),
            PropertyBlock(name="Datasheet", start=2, end=3, value="https://example.invalid/ds.pdf", hidden=True),
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
            PropertyBlock(name="Manufacturer", start=0, end=1, value="Texas Instruments", hidden=True),
            PropertyBlock(name="Description", start=1, end=2, value="Buck regulator", hidden=True),
            PropertyBlock(name="Datasheet", start=2, end=3, value="https://example.invalid/ds.pdf", hidden=True),
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
            PropertyBlock(name="Manufacturer", start=0, end=1, value="Texas Instruments", hidden=True),
            PropertyBlock(name="Description", start=1, end=2, value="Buck regulator", hidden=True),
            PropertyBlock(name="Datasheet", start=2, end=3, value="https://example.invalid/ds.pdf", hidden=True),
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


def test_validate_plan_rejects_generated_link_without_footprint_import() -> None:
    plan = make_plan(import_footprint=False, footprint_link=FootprintLinkChoice(mode="generated"))
    with pytest.raises(
        ImportErrorWithExitCode,
        match="generated footprint linking requires generated footprint import",
    ):
        validate_plan(plan, make_artifacts())


def test_render_summary_includes_creation_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.easyeda_import.importer.SYMBOL_DIR", tmp_path / "symbols")
    monkeypatch.setattr("scripts.easyeda_import.importer.FOOTPRINT_DIR", tmp_path / "footprints")
    summary = render_summary(make_plan(models_dir=tmp_path / "3d-models"), make_artifacts())
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


def test_resolve_models_dir_resolves_repo_relative_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.easyeda_import.importer.REPO_ROOT", tmp_path)
    assert resolve_models_dir("3d-models/custom", default="3d-models", interactive=False) == (
        tmp_path / "3d-models" / "custom"
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("C2040", "C2040"), (" c2040 ", "C2040")],
)
def test_normalize_lcsc_id_accepts_expected_format(raw_value: str, expected: str) -> None:
    assert normalize_lcsc_id(raw_value) == expected


def test_normalize_lcsc_id_rejects_invalid_prefix() -> None:
    with pytest.raises(ImportErrorWithExitCode, match="LCSC ID must start with C"):
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
def test_state_bool_handles_bool_and_string_values(raw_value: object, default: bool, expected: bool) -> None:
    state = {} if raw_value is None else {"flag": raw_value}
    assert state_bool(state, "flag", default) is expected


def test_stage_converter_output_tolerates_missing_3d_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_root = tmp_path / "tmp" / "easyeda-import"
    monkeypatch.setattr("scripts.easyeda_import.importer.TMP_ROOT", stage_root)

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

    monkeypatch.setattr("scripts.easyeda_import.importer.run_converter", fake_run_converter)

    artifacts = stage_converter_output(make_plan(stage_name="c2158003"))

    assert artifacts.staged_footprint_name == "SOIC-8"
    assert artifacts.staged_model_paths == []


def test_offer_setup_kicad_runs_setup_script_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[list[str], Path, bool]] = []

    def fake_run(args: list[str], cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd, check))
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("scripts.easyeda_import.importer.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.easyeda_import.importer.SETUP_KICAD_SCRIPT", Path("/tmp/setup-kicad.sh"))
    monkeypatch.setattr("scripts.easyeda_import.importer.REPO_ROOT", Path("/tmp/repo"))

    offer_setup_kicad(interactive=False)

    assert calls == [(["/tmp/setup-kicad.sh"], Path("/tmp/repo"), False)]
    assert "KiCad library setup refreshed." in capsys.readouterr().out


def test_offer_setup_kicad_skips_setup_when_declined_interactively(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("scripts.easyeda_import.importer.prompt_yes_no", lambda prompt, default: False)

    def fail_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("setup-kicad.sh should not run when declined")

    monkeypatch.setattr("scripts.easyeda_import.importer.subprocess.run", fail_run)

    offer_setup_kicad(interactive=True)

    assert "Run ./scripts/setup-kicad.sh to refresh KiCad library setup." in capsys.readouterr().out
