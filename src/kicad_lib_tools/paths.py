from __future__ import annotations

import re
from pathlib import Path

from .config import get_config


MODEL_EXTENSIONS: frozenset[str] = frozenset({".step", ".stp", ".wrl"})
PROPERTY_FONT_SIZE: float = 1.27


def __getattr__(name: str):  # noqa: N807 — module-level __getattr__
    """Lazily compute path constants from the current config."""
    cfg = get_config()
    root = cfg.repo_root
    _mapping = {
        "REPO_ROOT": root,
        "SYMBOL_DIR": root / cfg.symbol_dir,
        "FOOTPRINT_DIR": root / cfg.footprint_dir,
        "MODEL_ROOT": root / cfg.model_dir,
        "TMP_ROOT": root / cfg.tmp_dir,
        "STATE_FILE": root / cfg.state_file,
        "SETUP_KICAD_SCRIPT": root / cfg.setup_script,
        "VALIDATOR_SCRIPT": root / cfg.validator_script,
        "DEFAULT_CONVERTER": (root / cfg.default_converter_rel).resolve(),
    }
    if name in _mapping:
        return _mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
# Pure helpers (no config dependency)
# ---------------------------------------------------------------------------


def block_depth_delta(line: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for char in line:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
    return depth


def slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "part"


def escape_kicad_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def display_path(path: Path) -> str:
    from .config import get_config as _get_config
    repo_root = _get_config().repo_root
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def model_reference_path(destination: Path) -> str:
    from .config import get_config as _get_config
    cfg = _get_config()
    model_root = cfg.repo_root / cfg.model_dir
    try:
        relative_to_model_root = destination.resolve().relative_to(model_root.resolve())
        return "${" + cfg.model_env_var + "}/" + relative_to_model_root.as_posix()
    except ValueError:
        return destination.resolve().as_posix()


def models_dir_state_value(path: Path) -> str:
    from .config import get_config as _get_config
    repo_root = _get_config().repo_root
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())
