from __future__ import annotations

import re
from pathlib import Path

from .errors import ImportErrorWithExitCode
from .interaction import prompt_yes_no
from .paths import FOOTPRINT_DIR, REPO_ROOT, SYMBOL_DIR


VALID_LIBRARY_NAME = re.compile(r"^GS_[A-Za-z0-9][A-Za-z0-9_+-]*$")


def list_symbol_libraries() -> list[str]:
    return sorted(path.stem for path in SYMBOL_DIR.glob("*.kicad_sym"))


def list_footprint_libraries() -> list[str]:
    return sorted(path.stem for path in FOOTPRINT_DIR.glob("*.pretty"))


def list_library_footprints(library_name: str) -> list[str]:
    library_path = FOOTPRINT_DIR / f"{library_name}.pretty"
    if not library_path.is_dir():
        raise ImportErrorWithExitCode(
            f"footprint library does not exist: {library_path.relative_to(REPO_ROOT)}",
            exit_code=1,
        )
    return sorted(path.stem for path in library_path.glob("*.kicad_mod"))


def normalize_library_name(raw_name: str) -> str:
    value = raw_name.strip()
    if value.endswith(".kicad_sym"):
        value = value[: -len(".kicad_sym")]
    if value.endswith(".pretty"):
        value = value[: -len(".pretty")]
    if not VALID_LIBRARY_NAME.fullmatch(value):
        raise ImportErrorWithExitCode(
            f'invalid library name "{raw_name}": expected GS_<Category>',
            exit_code=1,
        )
    return value


def ensure_symbol_library(path: Path, interactive: bool) -> bool:
    if path.exists():
        return False
    if not interactive:
        raise ImportErrorWithExitCode(
            f"symbol library does not exist: {path.relative_to(REPO_ROOT)}",
            exit_code=1,
        )
    if not prompt_yes_no(
        f"Create symbol library {path.relative_to(REPO_ROOT)}?", default=True
    ):
        raise ImportErrorWithExitCode("symbol library creation declined", exit_code=1)
    create_symbol_library(path)
    return True


def ensure_footprint_library(path: Path, interactive: bool) -> bool:
    if path.exists():
        return False
    if not interactive:
        raise ImportErrorWithExitCode(
            f"footprint library does not exist: {path.relative_to(REPO_ROOT)}",
            exit_code=1,
        )
    if not prompt_yes_no(
        f"Create footprint library {path.relative_to(REPO_ROOT)}?", default=True
    ):
        raise ImportErrorWithExitCode("footprint library creation declined", exit_code=1)
    create_footprint_library(path)
    return True


def create_symbol_library(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "(kicad_symbol_lib\n"
        '\t(version 20241209)\n'
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "9.0")\n'
        ")\n",
        encoding="utf-8",
    )


def create_footprint_library(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
