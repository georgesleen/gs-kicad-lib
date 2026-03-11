from __future__ import annotations

import sys

from .cli import parse_args
from .errors import ImportErrorWithExitCode
from .importer import run_import


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        run_import(args)
    except ImportErrorWithExitCode as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except KeyboardInterrupt:
        print("Error: cancelled by user", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

