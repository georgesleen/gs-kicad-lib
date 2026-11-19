"""Table that maps LCSC part categories to symbol libraries."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path

from .errors import ImportErrorWithExitCode

HEADER = (
    "# LCSC category to symbol library. The importer adds an entry when you pick a\n"
    "# library for a part whose category has none. Edit freely.\n"
)


def load_category_libraries(path: Path) -> dict[str, str]:
    """Return the category table at ``path``, or an empty table if the file is absent.

    Raises:
        ImportErrorWithExitCode: if the file is not a flat table of strings.
    """
    if not path.is_file():
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as err:
        raise ImportErrorWithExitCode(f"{path.name}: {err}", exit_code=1) from err
    table: dict[str, str] = {}
    for category, library in raw.items():
        if not isinstance(library, str):
            raise ImportErrorWithExitCode(
                f"{path.name}: {category!r} must map to a library name", exit_code=1
            )
        table[category] = library
    return table


def render_category_libraries(table: Mapping[str, str]) -> str:
    """Return the TOML text for a category table, sorted by category."""
    lines = [
        f"{json.dumps(category, ensure_ascii=False)} = {json.dumps(library, ensure_ascii=False)}"
        for category, library in sorted(table.items(), key=lambda item: item[0].lower())
    ]
    return HEADER + "\n" + "\n".join(lines) + "\n"


def library_for_categories(table: Mapping[str, str], categories: list[str]) -> str | None:
    """Return the library of the first category in ``categories`` that the table maps."""
    return next((table[category] for category in categories if category in table), None)


def record_category_library(path: Path, category: str, library: str) -> bool:
    """Add ``category`` to the table at ``path`` unless it already has an entry.

    Returns:
        True if the table changed.
    """
    table = load_category_libraries(path)
    if not category or category in table:
        return False
    table[category] = library
    path.write_text(render_category_libraries(table), encoding="utf-8")
    return True
