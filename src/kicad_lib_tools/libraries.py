from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .config import get_config
from .errors import ImportErrorWithExitCode
from .interaction import prompt_yes_no
from .paths import display_path
from .symbols import get_first_property_value, parse_symbol_properties, parse_top_level_symbols
from .types import LcscId


def _valid_library_name_pattern() -> re.Pattern[str]:
    prefix = re.escape(get_config().library_prefix)
    return re.compile(rf"^{prefix}_[A-Za-z0-9][A-Za-z0-9_+-]*$")


def symbol_library_path(library_name: str) -> Path:
    """Return the file path of a symbol library in the repo."""
    return get_config().symbol_path / f"{library_name}.kicad_sym"


def footprint_library_path(library_name: str) -> Path:
    """Return the directory path of a footprint library in the repo."""
    return get_config().footprint_path / f"{library_name}.pretty"


def symbol_library_files() -> list[Path]:
    """Return the paths of all symbol libraries in the repo, sorted by name."""
    return sorted(get_config().symbol_path.glob("*.kicad_sym"))


def list_symbol_libraries() -> list[str]:
    return [path.stem for path in symbol_library_files()]


def list_footprint_libraries() -> list[str]:
    return sorted(path.stem for path in get_config().footprint_path.glob("*.pretty"))


def list_library_footprints(library_name: str) -> list[str]:
    library_path = footprint_library_path(library_name)
    if not library_path.is_dir():
        raise ImportErrorWithExitCode(
            f"footprint library does not exist: {display_path(library_path)}",
            exit_code=1,
        )
    return sorted(path.stem for path in library_path.glob("*.kicad_mod"))


def list_library_symbols(library_name: str) -> list[str]:
    """Return the top-level symbol names in a symbol library, in file order."""
    library_path = symbol_library_path(library_name)
    if not library_path.is_file():
        return []
    return [block.name for block in parse_top_level_symbols(library_path.read_text("utf-8"))]


def find_symbols_by_lcsc_id(lcsc_id: LcscId, library_paths: Iterable[Path]) -> list[str]:
    """Return ``Library:Symbol`` references for symbols whose LCSC ID field matches."""
    matches: list[str] = []
    for path in library_paths:
        for block in parse_top_level_symbols(path.read_text(encoding="utf-8")):
            properties = parse_symbol_properties(block.text)
            if get_first_property_value(properties, "LCSC ID") == lcsc_id:
                matches.append(f"{path.stem}:{block.name}")
    return matches


def suggest_library(category_text: str, libraries: Iterable[str]) -> str | None:
    """Return the library whose category words best match an LCSC category, or None.

    A library matches when every word of its name after the prefix starts some word of
    ``category_text``, ignoring case and a plural ``s``.
    """
    words = re.findall(r"[a-z0-9]+", category_text.lower())
    prefix = f"{get_config().library_prefix}_"
    best: tuple[int, str] | None = None
    for library in libraries:
        tokens = [
            token.lower().removesuffix("s") for token in library.removeprefix(prefix).split("_")
        ]
        if all(any(word.startswith(token) for word in words) for token in tokens):
            if best is None or len(tokens) > best[0]:
                best = (len(tokens), library)
    return best[1] if best else None


def normalize_library_name(raw_name: str) -> str:
    value = raw_name.strip()
    if value.endswith(".kicad_sym"):
        value = value[: -len(".kicad_sym")]
    if value.endswith(".pretty"):
        value = value[: -len(".pretty")]
    if not _valid_library_name_pattern().fullmatch(value):
        raise ImportErrorWithExitCode(
            f'invalid library name "{raw_name}": expected {get_config().library_prefix}_<Category>',
            exit_code=1,
        )
    return value


def ensure_symbol_library(path: Path, interactive: bool) -> bool:
    if path.exists():
        return False
    if not interactive:
        raise ImportErrorWithExitCode(
            f"symbol library does not exist: {display_path(path)}",
            exit_code=1,
        )
    if not prompt_yes_no(f"Create symbol library {display_path(path)}?", default=True):
        raise ImportErrorWithExitCode("symbol library creation declined", exit_code=1)
    create_symbol_library(path)
    return True


def ensure_footprint_library(path: Path, interactive: bool) -> bool:
    if path.exists():
        return False
    if not interactive:
        raise ImportErrorWithExitCode(
            f"footprint library does not exist: {display_path(path)}",
            exit_code=1,
        )
    if not prompt_yes_no(f"Create footprint library {display_path(path)}?", default=True):
        raise ImportErrorWithExitCode("footprint library creation declined", exit_code=1)
    create_footprint_library(path)
    return True


def create_symbol_library(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "(kicad_symbol_lib\n"
        "\t(version 20241209)\n"
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "9.0")\n'
        ")\n",
        encoding="utf-8",
    )


def create_footprint_library(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
