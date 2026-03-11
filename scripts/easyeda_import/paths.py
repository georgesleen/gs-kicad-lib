from __future__ import annotations

import re
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_DIR = SCRIPT_PATH.parent.parent
REPO_ROOT = SCRIPTS_DIR.parent
SYMBOL_DIR = REPO_ROOT / "symbols"
FOOTPRINT_DIR = REPO_ROOT / "footprints"
MODEL_ROOT = REPO_ROOT / "3d-models"
TMP_ROOT = REPO_ROOT / "tmp" / "easyeda-import"
STATE_FILE = REPO_ROOT / "tmp" / "easyeda-import-state.json"
SETUP_KICAD_SCRIPT = REPO_ROOT / "scripts" / "setup-kicad.sh"
VALIDATOR_SCRIPT = REPO_ROOT / "scripts" / "check-symbol-fields.py"
DEFAULT_CONVERTER = REPO_ROOT.parent / "easyeda2kicad.py" / ".venv" / "bin" / "python"
MODEL_EXTENSIONS = {".step", ".stp", ".wrl"}
PROPERTY_FONT_SIZE = 1.27


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
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def model_reference_path(destination: Path) -> str:
    try:
        relative_to_model_root = destination.resolve().relative_to(MODEL_ROOT.resolve())
        return "${GS_3DMODEL_DIR}/" + relative_to_model_root.as_posix()
    except ValueError:
        return destination.resolve().as_posix()


def models_dir_state_value(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
