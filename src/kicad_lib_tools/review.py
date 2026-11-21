from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import ImportErrorWithExitCode
from .interaction import Prompter
from .paths import display_path, escape_kicad_string
from .symbols import (
    SymbolBlock,
    get_first_property_value,
    parse_symbol_properties,
    parse_top_level_symbols,
    remove_symbol_from_library_text,
    render_symbol_library_update,
)
from .validation import check_files

KICAD_PROCESS_NAMES = frozenset({"kicad", "eeschema", "pcbnew"})
REVIEW_SCHEMATIC_NAME = "review"


@dataclass(frozen=True)
class FileChange:
    """A file that an import wrote, with its bytes from before the import.

    ``previous`` is ``None`` when the import created the file.
    """

    path: Path
    previous: bytes | None


@dataclass(frozen=True)
class SymbolChange:
    """A symbol that an import wrote into a library, with its block from before the import.

    ``previous_block`` is ``None`` when the import added a new symbol.
    """

    library: Path
    name: str
    previous_block: str | None


@dataclass(frozen=True)
class ImportRecord:
    """The library changes that one applied import made."""

    symbol: SymbolChange | None
    footprint: FileChange | None
    models: tuple[FileChange, ...]


def record_file(path: Path) -> FileChange:
    """Return a change record for a file that is about to be written."""
    return FileChange(path=path, previous=path.read_bytes() if path.exists() else None)


def record_symbol(library: Path, name: str) -> SymbolChange:
    """Return a change record for a symbol that is about to be written into a library."""
    previous = find_symbol(library.read_text(encoding="utf-8"), name) if library.exists() else None
    return SymbolChange(
        library=library,
        name=name,
        previous_block=previous.text if previous is not None else None,
    )


def find_symbol(library_text: str, name: str) -> SymbolBlock | None:
    """Return the first top-level symbol named ``name`` in a symbol library's text."""
    return next(
        (symbol for symbol in parse_top_level_symbols(library_text) if symbol.name == name),
        None,
    )


def render_review_schematic(library: str, symbol: SymbolBlock) -> str:
    """Return a one-sheet schematic that places one instance of a library symbol.

    ``symbol`` is the symbol's top-level block from the library named ``library``.
    """
    lib_id = f"{escape_kicad_string(library)}:{symbol.name}"
    cached_symbol = symbol.text.replace(f'(symbol "{symbol.name}"', f'(symbol "{lib_id}"', 1)
    reference = get_first_property_value(parse_symbol_properties(symbol.text), "Reference") or "U"
    sheet_uuid = uuid.uuid4()
    return f"""(kicad_sch
\t(version 20260306)
\t(generator "eeschema")
\t(generator_version "10.0")
\t(uuid "{sheet_uuid}")
\t(paper "A4")
\t(lib_symbols
{cached_symbol.rstrip()}
\t)
\t(symbol
\t\t(lib_id "{lib_id}")
\t\t(at 148.59 105.41 0)
\t\t(unit 1)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(uuid "{uuid.uuid4()}")
\t\t(property "Reference" "{reference}1" (at 148.59 95.25 0) (effects (font (size 1.27 1.27))))
\t\t(property "Value" "{symbol.name}" (at 148.59 115.57 0) (effects (font (size 1.27 1.27))))
\t\t(instances
\t\t\t(project "{REVIEW_SCHEMATIC_NAME}"
\t\t\t\t(path "/{sheet_uuid}" (reference "{reference}1") (unit 1))
\t\t\t)
\t\t)
\t)
\t(sheet_instances (path "/" (page "1")))
)
"""


def write_review_schematic(review_dir: Path, library: str, symbol: SymbolBlock) -> Path:
    """Write the review schematic and its project file, and return the schematic path."""
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / f"{REVIEW_SCHEMATIC_NAME}.kicad_pro").write_text("{}\n", encoding="utf-8")
    schematic = review_dir / f"{REVIEW_SCHEMATIC_NAME}.kicad_sch"
    schematic.write_text(render_review_schematic(library, symbol), encoding="utf-8")
    return schematic


def running_kicad_processes(proc_root: Path = Path("/proc")) -> list[str]:
    """Return the names of running KiCad GUI processes, or an empty list without procfs."""
    names: list[str] = []
    for comm in proc_root.glob("[0-9]*/comm"):
        try:
            name = comm.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if name in KICAD_PROCESS_NAMES:
            names.append(name)
    return sorted(names)


def editor_commands(schematic: Path | None, footprint: Path | None) -> list[list[str]]:
    """Return the commands that open the review schematic and the footprint editor."""
    commands: list[list[str]] = []
    if schematic is not None:
        commands.append(["eeschema", str(schematic.resolve())])
    if footprint is not None:
        commands.append(["kicad", "--frame", "fpedit", str(footprint.resolve())])
    return commands


def open_editors(commands: list[list[str]]) -> None:
    """Start each editor command and wait until all of them exit."""
    processes: list[subprocess.Popen[bytes]] = []
    for command in commands:
        try:
            processes.append(
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            )
        except FileNotFoundError:
            print(f"Warning: {command[0]} not found on PATH; skipping that editor.")
    for process in processes:
        process.wait()


def revert_import(record: ImportRecord) -> list[str]:
    """Undo the library changes in ``record`` and return a warning for each one it skipped.

    Only the imported symbol and the files the import wrote change; other edits to the same
    libraries stay.
    """
    warnings: list[str] = []
    if record.symbol is not None:
        warning = revert_symbol(record.symbol)
        if warning:
            warnings.append(warning)
    for change in (record.footprint, *record.models):
        if change is None:
            continue
        if change.previous is None:
            change.path.unlink(missing_ok=True)
        else:
            change.path.write_bytes(change.previous)
    return warnings


def revert_symbol(change: SymbolChange) -> str | None:
    """Undo one symbol change and return a warning if the symbol is no longer in its library."""
    text = change.library.read_text(encoding="utf-8")
    if find_symbol(text, change.name) is None:
        return (
            f"symbol {change.name} is no longer in {display_path(change.library)};"
            " it was not reverted"
        )
    if change.previous_block is None:
        updated = remove_symbol_from_library_text(text, change.name)
        change.library.write_text(updated, encoding="utf-8")
    else:
        updated = render_symbol_library_update(
            symbol_library_path=change.library,
            symbol_name=change.name,
            symbol_block=change.previous_block,
            overwrite=True,
        )
        change.library.write_text(updated, encoding="utf-8")
    return None


def review_import(record: ImportRecord, review_dir: Path, ui: Prompter) -> bool:
    """Open an applied import in the KiCad editors, validate it, and ask whether to keep it.

    Args:
        record: the library changes that the import made.
        review_dir: scratch directory for the review schematic.
        ui: source of the keep-or-revert answer.

    Returns:
        ``True`` if the user keeps the import; ``False`` after a revert.
    """
    others = running_kicad_processes()
    if others:
        print(
            "Warning: KiCad is already running (" + ", ".join(sorted(set(others))) + "). "
            "A window that has these libraries loaded can overwrite the import when it saves."
        )

    schematic = None
    if record.symbol is not None:
        library_text = record.symbol.library.read_text(encoding="utf-8")
        symbol = find_symbol(library_text, record.symbol.name)
        if symbol is None:
            raise ImportErrorWithExitCode(
                f"imported symbol {record.symbol.name} missing from"
                f" {display_path(record.symbol.library)}",
                exit_code=3,
            )
        schematic = write_review_schematic(review_dir, record.symbol.library.stem, symbol)
        print(
            "Review: click the symbol in the schematic and press Ctrl+Shift+E to edit it."
            " The review schematic itself is scratch; save or discard it."
        )
    footprint = record.footprint.path if record.footprint is not None else None
    if footprint is not None:
        print(
            "Review: the footprint opens detached from its library;"
            f" to keep edits, save it over {display_path(footprint)}."
        )
    print("Close all review windows to continue.")
    open_editors(editor_commands(schematic, footprint))

    valid = True
    if record.symbol is not None:
        report = check_files([record.symbol.library])
        valid = report.passed
        if not valid:
            print(report.render())

    if ui.yes_no("Keep this import?", default=valid):
        return True
    for warning in revert_import(record):
        print(f"Warning: {warning}")
    print("Import reverted.")
    return False
