"""Creation of a new, empty KiCad library."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import CONFIG_FILE, PREFIX_PATTERN, LibraryConfig

GITIGNORE_LINES = ("tmp/", "fp-info-cache")


def config_text(prefix: str) -> str:
    """Return the ``kicad-lib.toml`` text for a new library with ``prefix``."""
    return f'[tool.kicad-lib]\nlibrary_prefix = "{prefix}"\n'


def create_library(root: Path, prefix: str) -> list[Path]:
    """Create a library at ``root`` and return the paths it created.

    Raises:
        FileExistsError: if ``root`` already has a ``kicad-lib.toml``.
        ValueError: if ``prefix`` is not a valid library prefix.
    """
    if not PREFIX_PATTERN.fullmatch(prefix):
        raise ValueError(f"prefix {prefix!r} must be a letter followed by letters and digits")
    config_file = root / CONFIG_FILE
    if config_file.exists():
        raise FileExistsError(f"{config_file} already exists")

    config = LibraryConfig(repo_root=root, library_prefix=prefix)
    created: list[Path] = []
    for directory in (
        config.symbol_path,
        config.footprint_path,
        config.model_path,
        config.spice_model_path,
    ):
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(directory)

    config_file.write_text(config_text(prefix), encoding="utf-8")
    created.append(config_file)

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if missing:
        with gitignore.open("a", encoding="utf-8") as f:
            f.writelines(f"{line}\n" for line in missing)
        if not existing:
            created.append(gitignore)
    return created


def main(argv: list[str] | None = None) -> int:
    """Run ``kicad-lib init`` and return its exit code."""
    parser = argparse.ArgumentParser(
        prog="kicad-lib init",
        description="Create a new, empty KiCad library.",
    )
    parser.add_argument("path", nargs="?", default=".", help="Library directory (default: .)")
    parser.add_argument(
        "--prefix",
        required=True,
        help="Library name prefix, for example ACME for ACME_Connectors",
    )
    args = parser.parse_args(argv)
    root = Path(args.path).resolve()
    try:
        created = create_library(root, args.prefix)
    except (FileExistsError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    for path in created:
        print(f"Created {path}")
    print(f"Next: run kicad-lib setup in {root} to register the library with KiCad.")
    return 0
