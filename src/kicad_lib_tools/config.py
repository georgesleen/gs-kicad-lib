"""Configuration for kicad-lib-tools, loaded from kicad-lib.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PassiveTypeConfig:
    prefix: str
    value_param: str
    # Template with {package} placeholder; library prefix is NOT in template —
    # it comes from LibraryConfig.library_prefix so renaming the prefix is one change.
    library_name_template: str  # e.g. "{prefix}_Resistor_{package}"


@dataclass
class LibraryConfig:
    repo_root: Path
    symbol_dir: str = "symbols"
    footprint_dir: str = "footprints"
    model_dir: str = "3d-models"
    tmp_dir: str = "tmp/easyeda-import"
    state_file: str = "tmp/easyeda-import-state.json"
    setup_script: str = "scripts/setup-kicad.sh"
    validator_script: str = "scripts/check-symbol-fields.py"
    library_prefix: str = "GS"
    model_env_var: str = "GS_3DMODEL_DIR"
    converter_env_var: str = "GS_EASYEDA2KICAD_CMD"
    default_converter_rel: str = "../easyeda2kicad.py/.venv/bin/python"
    passive_types: dict[str, PassiveTypeConfig] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.passive_types is None:
            self.passive_types = _default_passive_types(self.library_prefix)


def _default_passive_types(prefix: str) -> dict[str, PassiveTypeConfig]:
    return {
        "Resistors": PassiveTypeConfig(
            prefix="R",
            value_param="Resistance",
            library_name_template=f"{prefix}_Resistor_{{package}}",
        ),
        "Capacitors": PassiveTypeConfig(
            prefix="C",
            value_param="Capacitance",
            library_name_template=f"{prefix}_Capacitor_{{package}}",
        ),
    }


def _find_repo_root() -> tuple[Path, dict]:
    """Walk up from CWD looking for kicad-lib.toml, then .git."""
    current = Path.cwd().resolve()
    for directory in [current, *current.parents]:
        config_file = directory / "kicad-lib.toml"
        if config_file.is_file():
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
            return directory, data.get("tool", {}).get("kicad-lib", {})
        if (directory / ".git").exists():
            return directory, {}
    return current, {}


_config: LibraryConfig | None = None


def get_config() -> LibraryConfig:
    """Return the current config, auto-discovering from CWD if needed."""
    global _config
    if _config is None:
        repo_root, raw = _find_repo_root()
        _config = _config_from_dict(repo_root, raw)
    return _config


def set_config(config: LibraryConfig) -> None:
    """Override the global config (useful for tests)."""
    global _config
    _config = config


def reset_config() -> None:
    """Clear the cached config so it reloads from disk on next call."""
    global _config
    _config = None


def _config_from_dict(repo_root: Path, raw: dict) -> LibraryConfig:
    prefix = raw.get("library_prefix", "GS")

    passive_raw = raw.get("passive_types", {})
    if passive_raw:
        passive_types: dict[str, PassiveTypeConfig] | None = {
            category: PassiveTypeConfig(**type_data)
            for category, type_data in passive_raw.items()
        }
    else:
        passive_types = None  # triggers __post_init__ default

    return LibraryConfig(
        repo_root=repo_root,
        symbol_dir=raw.get("symbol_dir", "symbols"),
        footprint_dir=raw.get("footprint_dir", "footprints"),
        model_dir=raw.get("model_dir", "3d-models"),
        tmp_dir=raw.get("tmp_dir", "tmp/easyeda-import"),
        state_file=raw.get("state_file", "tmp/easyeda-import-state.json"),
        setup_script=raw.get("setup_script", "scripts/setup-kicad.sh"),
        validator_script=raw.get("validator_script", "scripts/check-symbol-fields.py"),
        library_prefix=prefix,
        model_env_var=raw.get("model_env_var", "GS_3DMODEL_DIR"),
        converter_env_var=raw.get("converter_env_var", "GS_EASYEDA2KICAD_CMD"),
        default_converter_rel=raw.get(
            "default_converter_rel", "../easyeda2kicad.py/.venv/bin/python"
        ),
        passive_types=passive_types,
    )
