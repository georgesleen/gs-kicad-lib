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
    passive_types: dict[str, PassiveTypeConfig] | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.library_prefix:
            raise ValueError("library_prefix must not be empty")
        for field_name, value in [
            ("symbol_dir", self.symbol_dir),
            ("footprint_dir", self.footprint_dir),
            ("model_dir", self.model_dir),
        ]:
            if not value:
                raise ValueError(f"{field_name} must not be empty")
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


def _find_repo_root() -> tuple[Path, dict[str, object]]:
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


def _get_str(raw: dict[str, object], key: str, default: str) -> str:
    """Extract a string field from a raw TOML dict.

    Args:
        raw: parsed ``[tool.kicad-lib]`` section.
        key: TOML key to look up.
        default: value returned when ``key`` is absent.

    Raises:
        ValueError: if the key is present but not a string.
    """
    val = raw.get(key)
    if val is None:
        return default
    if not isinstance(val, str):
        raise ValueError(f"kicad-lib.toml: {key!r} must be a string, got {type(val).__name__!r}")
    return val


def _config_from_dict(repo_root: Path, raw: dict[str, object]) -> LibraryConfig:
    prefix = _get_str(raw, "library_prefix", "GS")

    passive_raw = raw.get("passive_types")
    if passive_raw is not None:
        if not isinstance(passive_raw, dict):
            raise ValueError("kicad-lib.toml: 'passive_types' must be a table")
        passive_types: dict[str, PassiveTypeConfig] | None = {
            category: PassiveTypeConfig(**type_data)
            for category, type_data in passive_raw.items()
        }
    else:
        passive_types = None  # triggers __post_init__ default

    return LibraryConfig(
        repo_root=repo_root,
        symbol_dir=_get_str(raw, "symbol_dir", "symbols"),
        footprint_dir=_get_str(raw, "footprint_dir", "footprints"),
        model_dir=_get_str(raw, "model_dir", "3d-models"),
        tmp_dir=_get_str(raw, "tmp_dir", "tmp/easyeda-import"),
        state_file=_get_str(raw, "state_file", "tmp/easyeda-import-state.json"),
        setup_script=_get_str(raw, "setup_script", "scripts/setup-kicad.sh"),
        validator_script=_get_str(raw, "validator_script", "scripts/check-symbol-fields.py"),
        library_prefix=prefix,
        model_env_var=_get_str(raw, "model_env_var", "GS_3DMODEL_DIR"),
        passive_types=passive_types,
    )
