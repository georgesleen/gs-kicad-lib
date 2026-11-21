"""Registration of the library's symbol and footprint libraries in KiCad."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from .config import LibraryConfig, get_config

KICAD_VERSION = "10.0"

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
    "Diodes": "discrete diodes and rectifiers",
}


def default_config_dir(version: str) -> Path:
    """Return the default KiCad config directory for the current OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "kicad" / version
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "kicad" / version
    return Path.home() / ".config" / "kicad" / version


def _normalize_token(token: str) -> str:
    if token in _TOKEN_MAP:
        return _TOKEN_MAP[token]
    if _PACKAGE_RE.match(token):
        return token
    return token.lower()


def library_description(lib_type: str, lib_name: str, prefix: str) -> str:
    """Generate a human-readable description for a KiCad library entry.

    Args:
        lib_type: ``"symbol"`` or ``"footprint"``.
        lib_name: Library nickname, e.g. ``GS_Resistor_0402``.
        prefix: Library prefix that the description leaves out, e.g. ``GS``.
    """
    raw = lib_name.removeprefix(f"{prefix}_")
    if raw in _LIB_OVERRIDES:
        stem = _LIB_OVERRIDES[raw]
    else:
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


def upsert_lib_entry(table_file: Path, lib_name: str, lib_uri: str, lib_descr: str) -> None:
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
    lines = [line for line in lines if f'(name "{lib_name}")' not in line]
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


def register_libraries(config: LibraryConfig, kicad_config_dir: Path) -> None:
    """Register every library in ``config`` with KiCad and set its path variables.

    Raises:
        FileNotFoundError: if the symbol or footprint directory does not exist.
    """
    for directory in (config.symbol_path, config.footprint_path):
        if not directory.is_dir():
            raise FileNotFoundError(f"library directory {directory} does not exist")

    sym_table = kicad_config_dir / "sym-lib-table"
    fp_table = kicad_config_dir / "fp-lib-table"
    ensure_table_file(sym_table, "(sym_lib_table")
    ensure_table_file(fp_table, "(fp_lib_table")
    for table in (sym_table, fp_table):
        backup = table.with_suffix(table.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(table, backup)

    prefix = config.library_prefix
    for sym_file in sorted(config.symbol_path.glob("*.kicad_sym")):
        upsert_lib_entry(
            sym_table,
            sym_file.stem,
            "${" + config.symbol_env_var + "}/" + sym_file.name,
            library_description("symbol", sym_file.stem, prefix),
        )
    for fp_dir in sorted(config.footprint_path.glob("*.pretty")):
        upsert_lib_entry(
            fp_table,
            fp_dir.stem,
            "${" + config.footprint_env_var + "}/" + fp_dir.name,
            library_description("footprint", fp_dir.stem, prefix),
        )

    path_vars = {
        config.symbol_env_var: str(config.symbol_path),
        config.footprint_env_var: str(config.footprint_path),
        config.model_env_var: str(config.model_path),
        config.spice_model_env_var: str(config.spice_model_path),
    }
    update_kicad_common(kicad_config_dir / "kicad_common.json", path_vars)
    print("Set KiCad path variables:")
    for name, value in path_vars.items():
        print(f"  {name}={value}")
    print()
    print(f"KiCad config dir: {kicad_config_dir}")
    print(f"Symbol table:     {sym_table}")
    print(f"Footprint table:  {fp_table}")


def main(argv: list[str] | None = None) -> int:
    """Run ``kicad-lib setup`` and return its exit code."""
    parser = argparse.ArgumentParser(
        prog="kicad-lib setup",
        description=(
            "Register the symbol and footprint libraries in KiCad and set its path variables."
        ),
    )
    parser.add_argument("--config-dir", help="Override KiCad config directory")
    parser.add_argument(
        "--kicad-version",
        default=KICAD_VERSION,
        metavar="VERSION",
        help=f"KiCad version directory (default: {KICAD_VERSION})",
    )
    args = parser.parse_args(argv)
    config_dir = (
        Path(args.config_dir) if args.config_dir else default_config_dir(args.kicad_version)
    )
    try:
        register_libraries(get_config(), config_dir)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
