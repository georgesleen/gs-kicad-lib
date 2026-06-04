#!/usr/bin/env python3
"""Set up gs-kicad-lib symbol and footprint libraries in KiCad."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

KICAD_VERSION = "10.0"
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

_TOKEN_MAP = {
    "THT": "through-hole",
    "SO": "small-outline",
    "IC": "integrated circuit",
    "MCU": "microcontroller",
    "IMU": "IMU",
    "PMIC": "PMIC",
    "EEPROM": "EEPROM",
    "LED": "LED",
}
_PACKAGE_RE = re.compile(r"^\d{4}[A-Za-z]*$")
_LIB_OVERRIDES: dict[str, str] = {
    "GS_Diodes": "discrete diodes and rectifiers",
}


def default_config_dir(version: str) -> Path:
    """Return the default KiCad config directory for the current OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "kicad" / version
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(
            Path.home() / "AppData" / "Roaming"
        )
        return Path(appdata) / "kicad" / version
    return Path.home() / ".config" / "kicad" / version


def _normalize_token(token: str) -> str:
    if token in _TOKEN_MAP:
        return _TOKEN_MAP[token]
    if _PACKAGE_RE.match(token):
        return token
    return token.lower()


def library_description(lib_type: str, lib_name: str) -> str:
    """Generate a human-readable description for a KiCad library entry.

    Args:
        lib_type: ``"symbol"`` or ``"footprint"``.
        lib_name: Library nickname, e.g. ``GS_Resistor_0402``.
    """
    if lib_name in _LIB_OVERRIDES:
        stem = _LIB_OVERRIDES[lib_name]
    else:
        raw = lib_name.removeprefix("GS_")
        tokens = [_normalize_token(t) for t in raw.split("_")]
        # If the last token is a package code, move it to the front.
        if len(tokens) >= 2 and _PACKAGE_RE.match(tokens[-1]):
            tokens = [tokens[-1]] + tokens[:-1]
        stem = " ".join(tokens)
    suffix = "symbol library" if lib_type == "symbol" else "footprint library"
    return f"{stem} {suffix}"


def _kicad_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def ensure_table_file(path: Path, header: str) -> None:
    """Create a KiCad table file with the given header if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"{header}\n)\n", encoding="utf-8")


def upsert_lib_entry(
    table_file: Path, lib_name: str, lib_uri: str, lib_descr: str
) -> None:
    """Insert or replace a library entry in a KiCad table file.

    Args:
        table_file: Path to ``sym-lib-table`` or ``fp-lib-table``.
        lib_name: Library nickname.
        lib_uri: URI string (may contain ``${VAR}`` references).
        lib_descr: Human-readable description.
    """
    entry = (
        f'  (lib (name "{_kicad_escape(lib_name)}")'
        f'(type "KiCad")'
        f'(uri "{_kicad_escape(lib_uri)}")'
        f'(options "")'
        f'(descr "{_kicad_escape(lib_descr)}"))'
    )
    lines = table_file.read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines if f'(name "{lib_name}")' not in l]
    while lines and lines[-1].strip() == ")":
        lines.pop()
    lines.append(entry)
    lines.append(")")
    table_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Configured: {lib_name}")


def update_kicad_common(json_file: Path, vars: dict[str, str]) -> None:
    """Merge path variables into ``kicad_common.json``.

    Args:
        json_file: Path to ``kicad_common.json``.
        vars: Mapping of variable name to path string.
    """
    json_file.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {}
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    environment = data.get("environment")
    if not isinstance(environment, dict):
        environment = {}
    env_vars = environment.get("vars")
    if not isinstance(env_vars, dict):
        env_vars = {}
    env_vars.update(vars)
    environment["vars"] = env_vars
    data["environment"] = environment
    json_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the KiCad setup: register libraries and set path variables."""
    parser = argparse.ArgumentParser(
        description=(
            "Set up gs-kicad-lib in KiCad by registering symbol/footprint "
            "libraries and configuring path variables."
        )
    )
    parser.add_argument("--config-dir", help="Override KiCad config directory")
    parser.add_argument(
        "--kicad-version",
        default=KICAD_VERSION,
        metavar="VERSION",
        help=f"KiCad version directory (default: {KICAD_VERSION})",
    )
    args = parser.parse_args(argv)

    version: str = args.kicad_version
    config_dir = (
        Path(args.config_dir) if args.config_dir else default_config_dir(version)
    )

    symbol_dir = REPO_ROOT / "symbols"
    footprint_dir = REPO_ROOT / "footprints"
    model_dir = REPO_ROOT / "3d-models"
    spice_model_dir = REPO_ROOT / "spice-models"

    if not symbol_dir.is_dir() or not footprint_dir.is_dir():
        print(
            "Error: script must be run from inside gs-kicad-lib repo.",
            file=sys.stderr,
        )
        return 1

    sym_table = config_dir / "sym-lib-table"
    fp_table = config_dir / "fp-lib-table"
    common_json = config_dir / "kicad_common.json"

    ensure_table_file(sym_table, "(sym_lib_table")
    ensure_table_file(fp_table, "(fp_lib_table")

    for table in (sym_table, fp_table):
        backup = table.with_suffix(table.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(table, backup)

    for sym_file in sorted(symbol_dir.glob("*.kicad_sym")):
        upsert_lib_entry(
            sym_table,
            sym_file.stem,
            "${GS_SYMBOL_DIR}/" + sym_file.name,
            library_description("symbol", sym_file.stem),
        )

    for fp_dir in sorted(footprint_dir.glob("*.pretty")):
        upsert_lib_entry(
            fp_table,
            fp_dir.stem,
            "${GS_FOOTPRINT_DIR}/" + fp_dir.name,
            library_description("footprint", fp_dir.stem),
        )

    path_vars = {
        "GS_SYMBOL_DIR": str(symbol_dir),
        "GS_FOOTPRINT_DIR": str(footprint_dir),
        "GS_3DMODEL_DIR": str(model_dir),
        "GS_SPICE_MODEL_DIR": str(spice_model_dir),
    }
    update_kicad_common(common_json, path_vars)
    print("Set KiCad path variables:")
    for k, v in path_vars.items():
        print(f"  {k}={v}")

    print()
    print("Setup complete.")
    print(f"KiCad config dir: {config_dir}")
    print(f"Symbol table:     {sym_table}")
    print(f"Footprint table:  {fp_table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
