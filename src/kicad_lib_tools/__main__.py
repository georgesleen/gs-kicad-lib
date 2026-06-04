from __future__ import annotations

import sys

from .cli import parse_args
from .errors import ImportErrorWithExitCode
from .importer import run_import
from .main_menu import run_main_menu


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``kicad-lib-import``: parse args and run a single import.

    Args:
        argv: argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (0 on success, the error's exit_code on failure).
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        run_import(args)
    except ImportErrorWithExitCode as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(run_main_menu())
