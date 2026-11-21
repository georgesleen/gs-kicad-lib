"""Configuration for kicad-lib-tools, loaded from kicad-lib.toml."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TypedDict


class ConfigError(ValueError):
    """An invalid ``kicad-lib.toml`` setting."""


@dataclass
class PassiveTypeConfig:
    prefix: str
    value_param: str
    # Template with {package} placeholder; library prefix is NOT in template —
    # it comes from LibraryConfig.library_prefix so renaming the prefix is one change.
    library_name_template: str  # e.g. "{prefix}_Resistor_{package}"


@dataclass(frozen=True)
class FieldNames:
    """Names of the symbol fields that the tools write and validate."""

    manufacturer: str = "Manufacturer"
    mpn: str = "MPN"
    lcsc_id: str = "LCSC ID"
    package: str = "Package"
    validation_override: str = "Field Validation Override"
    spice_warning_override: str = "SPICE Warning Override"

    @property
    def procurement(self) -> tuple[str, ...]:
        """Fields that every BOM symbol must have, hidden."""
        return (self.manufacturer, self.mpn, self.lcsc_id, self.package)


@dataclass(frozen=True)
class FamilyFormat:
    """Format strings that build a part family's symbol name, Value, Description, and Reference.

    Each Description part is formatted on its own, and parts that come out empty are dropped.
    An empty ``reference`` keeps the reference designator of the source symbol.
    """

    name: str
    value: str
    description: tuple[str, ...]
    reference: str = ""


class FamilyFormatOverride(TypedDict, total=False):
    """The fields of a ``FamilyFormat`` that one ``[families.<family>]`` table replaces."""

    name: str
    value: str
    description: tuple[str, ...]
    reference: str


PREFIX_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]*")


@dataclass
class LibraryConfig:
    repo_root: Path
    library_prefix: str
    symbol_dir: str = "symbols"
    footprint_dir: str = "footprints"
    model_dir: str = "3d-models"
    spice_model_dir: str = "spice-models"
    tmp_dir: str = "tmp/easyeda-import"
    state_file: str = "tmp/easyeda-import-state.json"
    category_file: str = "library-categories.toml"
    libraries_md_file: str = "LIBRARIES.md"
    passive_types: dict[str, PassiveTypeConfig] | None = field(default=None)
    fields: FieldNames = field(default_factory=FieldNames)
    library_descriptions: dict[str, str] = field(default_factory=dict)
    description_words: dict[str, str] = field(default_factory=dict)
    family_formats: dict[str, FamilyFormatOverride] = field(default_factory=dict)

    @property
    def symbol_path(self) -> Path:
        """Absolute path of the symbol library directory."""
        return self.repo_root / self.symbol_dir

    @property
    def footprint_path(self) -> Path:
        """Absolute path of the footprint library directory."""
        return self.repo_root / self.footprint_dir

    @property
    def model_path(self) -> Path:
        """Absolute path of the 3D model directory."""
        return self.repo_root / self.model_dir

    @property
    def spice_model_path(self) -> Path:
        """Absolute path of the SPICE model directory."""
        return self.repo_root / self.spice_model_dir

    @property
    def symbol_env_var(self) -> str:
        """KiCad path variable that points at the symbol library directory."""
        return f"{self.library_prefix}_SYMBOL_DIR"

    @property
    def footprint_env_var(self) -> str:
        """KiCad path variable that points at the footprint library directory."""
        return f"{self.library_prefix}_FOOTPRINT_DIR"

    @property
    def model_env_var(self) -> str:
        """KiCad path variable that points at the 3D model directory."""
        return f"{self.library_prefix}_3DMODEL_DIR"

    @property
    def spice_model_env_var(self) -> str:
        """KiCad path variable that points at the SPICE model directory."""
        return f"{self.library_prefix}_SPICE_MODEL_DIR"

    @property
    def tmp_path(self) -> Path:
        """Absolute path of the import staging directory."""
        return self.repo_root / self.tmp_dir

    @property
    def state_path(self) -> Path:
        """Absolute path of the saved import choices file."""
        return self.repo_root / self.state_file

    @property
    def libraries_md_path(self) -> Path:
        """Absolute path of the generated symbol index."""
        return self.repo_root / self.libraries_md_file

    @property
    def category_file_path(self) -> Path:
        """Absolute path of the LCSC category to symbol library table."""
        return self.repo_root / self.category_file

    def __post_init__(self) -> None:
        if not PREFIX_PATTERN.fullmatch(self.library_prefix):
            raise ConfigError(
                f"library_prefix {self.library_prefix!r} must be a letter followed by"
                " letters and digits"
            )
        for field_name, value in [
            ("symbol_dir", self.symbol_dir),
            ("footprint_dir", self.footprint_dir),
            ("model_dir", self.model_dir),
            ("spice_model_dir", self.spice_model_dir),
        ]:
            if not value:
                raise ConfigError(f"{field_name} must not be empty")
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


CONFIG_FILE = "kicad-lib.toml"


def _find_repo_root() -> tuple[Path, dict[str, object]]:
    """Return the nearest directory at or above CWD with a kicad-lib.toml, and its settings.

    Raises:
        ConfigError: if no directory up to the filesystem root has one.
    """
    current = Path.cwd().resolve()
    for directory in [current, *current.parents]:
        config_file = directory / CONFIG_FILE
        if config_file.is_file():
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
            return directory, data.get("tool", {}).get("kicad-lib", {})
    raise ConfigError(
        f"no {CONFIG_FILE} in {current} or above; run kicad-lib init to create a library"
    )


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


_STRING_KEYS = (
    "symbol_dir",
    "footprint_dir",
    "model_dir",
    "spice_model_dir",
    "tmp_dir",
    "state_file",
    "category_file",
    "libraries_md_file",
    "library_prefix",
)
_TABLE_KEYS = (
    "passive_types",
    "fields",
    "library_descriptions",
    "description_words",
    "families",
)


def _get_str(raw: dict[str, object], key: str, default: str) -> str:
    """Extract a string field from a raw TOML dict.

    Args:
        raw: parsed ``[tool.kicad-lib]`` section or one of its tables.
        key: TOML key to look up.
        default: value returned when ``key`` is absent.

    Raises:
        ConfigError: if the key is present but not a string.
    """
    val = raw.get(key)
    if val is None:
        return default
    if not isinstance(val, str):
        raise ConfigError(f"kicad-lib.toml: {key!r} must be a string, got {type(val).__name__!r}")
    return val


def _get_table(raw: dict[str, object], key: str) -> dict[str, object] | None:
    val = raw.get(key)
    if val is not None and not isinstance(val, dict):
        raise ConfigError(f"kicad-lib.toml: {key!r} must be a table")
    return val


def _string_table(raw: dict[str, object], key: str) -> dict[str, str]:
    table = _get_table(raw, key) or {}
    return {name: _get_str(table, name, "") for name in table}


def _reject_unknown(table: str, raw: dict[str, object], known: set[str]) -> None:
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"kicad-lib.toml: unknown key(s) in {table}: {', '.join(unknown)}")


def _field_names(raw: dict[str, object] | None) -> FieldNames:
    if raw is None:
        return FieldNames()
    defaults = FieldNames()
    names = {f.name for f in fields(FieldNames)}
    _reject_unknown("[tool.kicad-lib.fields]", raw, names)
    return FieldNames(**{name: _get_str(raw, name, getattr(defaults, name)) for name in names})


def _passive_type(category: str, raw: dict[str, object] | None) -> PassiveTypeConfig:
    table = f"[tool.kicad-lib.passive_types.{category}]"
    names = {f.name for f in fields(PassiveTypeConfig)}
    _reject_unknown(table, raw or {}, names)
    values = {name: _get_str(raw or {}, name, "") for name in names}
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise ConfigError(f"kicad-lib.toml: {table} needs {', '.join(missing)}")
    return PassiveTypeConfig(**values)


def _family_format(family: str, raw: dict[str, object] | None) -> FamilyFormatOverride:
    table = f"[tool.kicad-lib.families.{family}]"
    raw = raw or {}
    _reject_unknown(table, raw, {"name", "value", "description", "reference"})
    override: FamilyFormatOverride = {}
    for key in ("name", "value", "reference"):
        if key in raw:
            override[key] = _get_str(raw, key, "")
    if "description" in raw:
        parts = raw["description"]
        if not isinstance(parts, list) or not all(isinstance(part, str) for part in parts):
            raise ConfigError(f"kicad-lib.toml: {table} description must be a list of strings")
        override["description"] = tuple(parts)
    return override


def _config_from_dict(repo_root: Path, raw: dict[str, object]) -> LibraryConfig:
    _reject_unknown("[tool.kicad-lib]", raw, {*_STRING_KEYS, *_TABLE_KEYS})
    if "library_prefix" not in raw:
        raise ConfigError("kicad-lib.toml: [tool.kicad-lib] needs library_prefix")
    defaults = LibraryConfig(
        repo_root=repo_root, library_prefix=_get_str(raw, "library_prefix", "")
    )
    strings = {key: _get_str(raw, key, getattr(defaults, key)) for key in _STRING_KEYS}

    passive_raw = _get_table(raw, "passive_types")
    passive_types = (
        {
            category: _passive_type(category, _get_table(passive_raw, category))
            for category in passive_raw
        }
        if passive_raw is not None
        else None
    )

    families = _get_table(raw, "families") or {}
    return LibraryConfig(
        repo_root=repo_root,
        symbol_dir=strings["symbol_dir"],
        footprint_dir=strings["footprint_dir"],
        model_dir=strings["model_dir"],
        spice_model_dir=strings["spice_model_dir"],
        tmp_dir=strings["tmp_dir"],
        state_file=strings["state_file"],
        category_file=strings["category_file"],
        libraries_md_file=strings["libraries_md_file"],
        library_prefix=strings["library_prefix"],
        passive_types=passive_types,
        fields=_field_names(_get_table(raw, "fields")),
        library_descriptions=_string_table(raw, "library_descriptions"),
        description_words=_string_table(raw, "description_words"),
        family_formats={
            family: _family_format(family, _get_table(families, family)) for family in families
        },
    )
