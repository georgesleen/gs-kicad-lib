"""The ``kicad-lib`` command line."""

from __future__ import annotations

import sys
from collections.abc import Callable

from . import kicad_setup, libraries_md, validation
from .cli import parse_args
from .config import ConfigError
from .errors import ImportErrorWithExitCode
from .importer import run_import
from .main_menu import run_main_menu
from .passive_creator import run_passive_creator


def import_command(argv: list[str]) -> int:
    """Run ``kicad-lib import`` and return its exit code."""
    args = parse_args(argv)
    try:
        run_import(args)
    except ImportErrorWithExitCode as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except KeyboardInterrupt:
        return 130
    return 0


COMMANDS: dict[str, tuple[Callable[[list[str]], int], str]] = {
    "import": (import_command, "import a part from LCSC through EasyEDA"),
    "passive": (run_passive_creator, "add a derived passive symbol from an LCSC ID"),
    "validate": (validation.main, "check symbol fields against the library conventions"),
    "setup": (kicad_setup.main, "register the libraries and path variables in KiCad"),
    "libraries-md": (libraries_md.main, "regenerate the symbol index"),
}


def usage() -> str:
    """Return the top-level help text."""
    width = max(len(name) for name in COMMANDS)
    lines = [
        "usage: kicad-lib [command] [args...]",
        "",
        "With no command, kicad-lib opens the interactive menu.",
        "",
        "commands:",
    ]
    lines += [f"  {name:<{width}}  {summary}" for name, (_, summary) in COMMANDS.items()]
    lines += ["", "Run kicad-lib <command> --help for the options of a command."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run ``kicad-lib`` with ``argv`` (default ``sys.argv[1:]``) and return its exit code."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        try:
            return run_main_menu()
        except ConfigError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 2
    name, rest = args[0], args[1:]
    if name in ("-h", "--help"):
        print(usage())
        return 0
    command = COMMANDS.get(name)
    if command is None:
        print(f"kicad-lib: unknown command {name!r}\n\n{usage()}", file=sys.stderr)
        return 2
    try:
        return command[0](rest)
    except ConfigError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
