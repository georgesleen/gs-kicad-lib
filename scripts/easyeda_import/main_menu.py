"""Top-level TUI menu for gs-kicad-lib tooling."""

from __future__ import annotations

import sys

from .cli import parse_args as parse_import_args
from .errors import ImportErrorWithExitCode
from .importer import run_import
from .passive_creator import run_passive_creator
from .selectors import SelectionOption, select_one


_MENU_OPTIONS = [
    SelectionOption(
        "import",
        "Import part from LCSC",
        "full symbol + footprint + 3D via easyeda2kicad",
    ),
    SelectionOption(
        "passive",
        "Add derived passive symbol",
        "resistor or capacitor — LCSC lookup only, no easyeda2kicad",
    ),
    SelectionOption("quit", "Quit"),
]


def run_main_menu() -> int:
    while True:
        try:
            choice = select_one(
                title="gs-kicad-lib",
                options=_MENU_OPTIONS,
                max_visible=len(_MENU_OPTIONS),
            )
        except (ImportErrorWithExitCode, KeyboardInterrupt):
            return 0

        if choice.value == "quit":
            return 0

        print()
        try:
            if choice.value == "import":
                run_import(parse_import_args([]))
            elif choice.value == "passive":
                run_passive_creator([])
        except ImportErrorWithExitCode as err:
            print(f"Error: {err}", file=sys.stderr)
        except KeyboardInterrupt:
            print()

        print()
