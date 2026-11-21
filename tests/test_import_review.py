from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from kicad_lib_tools import review
from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.paths import block_depth_delta
from kicad_lib_tools.review import (
    FileChange,
    ImportRecord,
    SymbolChange,
    editor_commands,
    find_symbol,
    record_file,
    record_symbol,
    render_review_schematic,
    revert_import,
    review_import,
    running_kicad_processes,
)
from kicad_lib_tools.symbols import remove_symbol_from_library_text
from kicad_lib_tools.validation import ValidationReport
from tests.fakes import ScriptedPrompter


def symbol_text(name: str, reference: str = "U", body: str = "") -> str:
    return (
        f'\t(symbol "{name}"\n'
        f'\t\t(property "Reference" "{reference}" (at 0 2.54 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Value" "{name}" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(symbol "{name}_0_1"\n'
        "\t\t\t(rectangle (start -2.54 2.54) (end 2.54 -2.54)"
        " (stroke (width 0.254) (type default)) (fill (type background)))\n"
        "\t\t)\n"
        f"{body}"
        "\t)\n"
    )


def library_text(*symbols: str) -> str:
    return (
        '(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "test")\n' + "".join(symbols) + ")\n"
    )


def test_remove_symbol_from_library_text_keeps_other_symbols_exactly() -> None:
    text = library_text(symbol_text("A"), symbol_text("B"), symbol_text("C"))

    assert remove_symbol_from_library_text(text, "B") == library_text(
        symbol_text("A"), symbol_text("C")
    )


def test_remove_symbol_from_library_text_rejects_missing_symbol() -> None:
    with pytest.raises(ImportErrorWithExitCode):
        remove_symbol_from_library_text(library_text(symbol_text("A")), "B")


def test_record_file_captures_previous_bytes(tmp_path: Path) -> None:
    existing = tmp_path / "old.step"
    existing.write_bytes(b"old")

    assert record_file(existing) == FileChange(path=existing, previous=b"old")
    assert record_file(tmp_path / "new.step") == FileChange(
        path=tmp_path / "new.step", previous=None
    )


def test_record_symbol_captures_previous_block(tmp_path: Path) -> None:
    library = tmp_path / "GS_IC.kicad_sym"
    library.write_text(library_text(symbol_text("A")), encoding="utf-8")

    assert record_symbol(library, "A").previous_block == symbol_text("A")
    assert record_symbol(library, "B").previous_block is None


def test_revert_removes_new_symbol_and_keeps_edits_to_other_symbols(tmp_path: Path) -> None:
    library = tmp_path / "GS_IC.kicad_sym"
    library.write_text(
        library_text(symbol_text("A", body="\t\t(edited during review)\n"), symbol_text("NEW")),
        encoding="utf-8",
    )
    record = ImportRecord(
        symbol=SymbolChange(library=library, name="NEW", previous_block=None),
        footprint=None,
        models=(),
    )

    assert revert_import(record) == []
    assert library.read_text(encoding="utf-8") == library_text(
        symbol_text("A", body="\t\t(edited during review)\n")
    )


def test_revert_restores_overwritten_symbol(tmp_path: Path) -> None:
    library = tmp_path / "GS_IC.kicad_sym"
    library.write_text(library_text(symbol_text("A", reference="NEW")), encoding="utf-8")
    record = ImportRecord(
        symbol=SymbolChange(library=library, name="A", previous_block=symbol_text("A")),
        footprint=None,
        models=(),
    )

    revert_import(record)

    assert library.read_text(encoding="utf-8") == library_text(symbol_text("A"))


def test_revert_warns_when_symbol_was_renamed(tmp_path: Path) -> None:
    library = tmp_path / "GS_IC.kicad_sym"
    original = library_text(symbol_text("RENAMED"))
    library.write_text(original, encoding="utf-8")
    record = ImportRecord(
        symbol=SymbolChange(library=library, name="NEW", previous_block=None),
        footprint=None,
        models=(),
    )

    warnings = revert_import(record)

    assert len(warnings) == 1 and "NEW" in warnings[0]
    assert library.read_text(encoding="utf-8") == original


def test_revert_deletes_created_files_and_restores_overwritten_ones(tmp_path: Path) -> None:
    created = tmp_path / "Part.kicad_mod"
    overwritten = tmp_path / "Part.step"
    untouched = tmp_path / "Other.kicad_mod"
    for path in (created, overwritten, untouched):
        path.write_bytes(b"current")
    record = ImportRecord(
        symbol=None,
        footprint=FileChange(path=created, previous=None),
        models=(FileChange(path=overwritten, previous=b"before"),),
    )

    revert_import(record)

    assert not created.exists()
    assert overwritten.read_bytes() == b"before"
    assert untouched.read_bytes() == b"current"


def test_render_review_schematic_places_library_symbol() -> None:
    symbol = find_symbol(library_text(symbol_text("LM311", reference="U")), "LM311")
    assert symbol is not None

    schematic = render_review_schematic("GS_Comparators", symbol)

    assert sum(block_depth_delta(line) for line in schematic.splitlines()) == 0
    assert '(symbol "GS_Comparators:LM311"' in schematic
    assert '(symbol "LM311_0_1"' in schematic
    assert '(lib_id "GS_Comparators:LM311")' in schematic
    assert '(reference "U1")' in schematic


@pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="kicad-cli not installed")
def test_render_review_schematic_loads_in_kicad(tmp_path: Path) -> None:
    symbol = find_symbol(library_text(symbol_text("LM311")), "LM311")
    assert symbol is not None
    schematic = review.write_review_schematic(tmp_path, "GS_Comparators", symbol)

    result = subprocess.run(
        ["kicad-cli", "sch", "export", "svg", "-o", str(tmp_path / "svg"), str(schematic)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_running_kicad_processes_reads_procfs(tmp_path: Path) -> None:
    for pid, name in {"1": "eeschema", "2": "bash", "3": "kicad", "x": "pcbnew"}.items():
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "comm").write_text(f"{name}\n", encoding="utf-8")

    assert running_kicad_processes(tmp_path) == ["eeschema", "kicad"]


def test_editor_commands_open_schematic_and_footprint(tmp_path: Path) -> None:
    schematic = tmp_path / "review.kicad_sch"
    footprint = tmp_path / "Part.kicad_mod"

    assert editor_commands(schematic, footprint) == [
        ["eeschema", str(schematic)],
        ["kicad", "--frame", "fpedit", str(footprint)],
    ]
    assert editor_commands(None, None) == []


@dataclass
class ReviewEnv:
    library: Path
    validator_rc: int = 0
    commands: list[list[str]] = field(default_factory=list)


@pytest.fixture
def review_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ReviewEnv:
    env = ReviewEnv(library=tmp_path / "GS_IC.kicad_sym")
    env.library.write_text(library_text(symbol_text("NEW")), encoding="utf-8")

    monkeypatch.setattr(review, "running_kicad_processes", lambda: [])
    monkeypatch.setattr(review, "open_editors", env.commands.extend)
    monkeypatch.setattr(
        review,
        "check_files",
        lambda files: ValidationReport(
            file_count=len(files),
            violations={"GS_IC:NEW": ["bad field"]} if env.validator_rc else {},
        ),
    )
    return env


def make_record(library: Path) -> ImportRecord:
    return ImportRecord(
        symbol=SymbolChange(library=library, name="NEW", previous_block=None),
        footprint=None,
        models=(),
    )


def test_review_import_keeps_import_when_accepted(review_env: ReviewEnv, tmp_path: Path) -> None:
    ui = ScriptedPrompter([""])
    assert review_import(make_record(review_env.library), tmp_path / "review", ui) is True
    assert [question.default for question in ui.questions] == [True]
    assert find_symbol(review_env.library.read_text(encoding="utf-8"), "NEW") is not None
    assert review_env.commands == [["eeschema", str(tmp_path / "review" / "review.kicad_sch")]]


def test_review_import_reverts_when_declined_and_defaults_to_no_on_invalid(
    review_env: ReviewEnv, tmp_path: Path
) -> None:
    review_env.validator_rc = 1

    ui = ScriptedPrompter(["n"])
    assert review_import(make_record(review_env.library), tmp_path / "review", ui) is False
    assert [question.default for question in ui.questions] == [False]
    assert find_symbol(review_env.library.read_text(encoding="utf-8"), "NEW") is None
