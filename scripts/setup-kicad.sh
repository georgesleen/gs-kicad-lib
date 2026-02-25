#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

KICAD_VERSION="9.0"
CONFIG_DIR="${HOME}/.config/kicad/${KICAD_VERSION}"
SYM_TABLE="${CONFIG_DIR}/sym-lib-table"
FP_TABLE="${CONFIG_DIR}/fp-lib-table"
COMMON_JSON="${CONFIG_DIR}/kicad_common.json"
GS_SYMBOL_DIR="${REPO_ROOT}/symbols"
GS_FOOTPRINT_DIR="${REPO_ROOT}/footprints"
GS_3DMODEL_DIR="${REPO_ROOT}/3d-models"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--config-dir DIR] [--kicad-version VERSION]

Sets up gs-kicad-lib in KiCad by:
- adding all symbol libraries in symbols/*.kicad_sym to global sym-lib-table
- adding all footprint libraries in footprints/*.pretty to global fp-lib-table
- setting GS_SYMBOL_DIR, GS_FOOTPRINT_DIR, and GS_3DMODEL_DIR in kicad_common.json
  (if jq is available)

Options:
  --config-dir DIR       Override KiCad config directory
                         (default: ~/.config/kicad/<version>)
  --kicad-version VER    KiCad version directory (default: 9.0)
  -h, --help             Show this help
USAGE
}

escape_for_kicad() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

ensure_table_file() {
  local file="$1"
  local header="$2"
  mkdir -p "$(dirname "$file")"
  if [[ ! -f "$file" ]]; then
    printf '%s\n)\n' "$header" > "$file"
  fi
}

upsert_lib_entry() {
  local table_file="$1"
  local lib_name="$2"
  local lib_uri="$3"

  local escaped_name escaped_uri entry tmp
  escaped_name="$(escape_for_kicad "$lib_name")"
  escaped_uri="$(escape_for_kicad "$lib_uri")"
  entry="  (lib (name \"${escaped_name}\")(type \"KiCad\")(uri \"${escaped_uri}\")(options \"\")(descr \"gs-kicad-lib\"))"

  tmp="$(mktemp)"
  sed '$d' "$table_file" | grep -Fv "(name \"${lib_name}\")" > "$tmp" || true
  printf '%s\n)\n' "$entry" >> "$tmp"
  mv "$tmp" "$table_file"

  echo "Configured: ${lib_name}"
}

update_env_vars_in_common_json() {
  local json_file="$1"
  local symbol_dir="$2"
  local footprint_dir="$3"
  local model_dir="$4"
  local python_bin=""

  if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    python_bin="python"
  fi

  mkdir -p "$(dirname "$json_file")"
  if [[ ! -f "$json_file" ]]; then
    printf '{}\n' > "$json_file"
  fi

  if command -v jq >/dev/null 2>&1; then
    local tmp
    tmp="$(mktemp)"
    jq --arg symbol_dir "$symbol_dir" \
       --arg footprint_dir "$footprint_dir" \
       --arg model_dir "$model_dir" '
      .environment |= (. // {})
      | .environment.vars |= (. // {})
      | .environment.vars.GS_SYMBOL_DIR = $symbol_dir
      | .environment.vars.GS_FOOTPRINT_DIR = $footprint_dir
      | .environment.vars.GS_3DMODEL_DIR = $model_dir
    ' "$json_file" > "$tmp"
    mv "$tmp" "$json_file"
  elif [[ -n "$python_bin" ]]; then
    JSON_FILE="$json_file" \
    GS_SYMBOL_DIR="$symbol_dir" \
    GS_FOOTPRINT_DIR="$footprint_dir" \
    GS_3DMODEL_DIR="$model_dir" \
    "$python_bin" - <<'PY'
import json
import os
from pathlib import Path

json_file = Path(os.environ["JSON_FILE"])
symbol_dir = os.environ["GS_SYMBOL_DIR"]
footprint_dir = os.environ["GS_FOOTPRINT_DIR"]
model_dir = os.environ["GS_3DMODEL_DIR"]

data = {}
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
vars_obj = environment.get("vars")
if not isinstance(vars_obj, dict):
    vars_obj = {}

vars_obj["GS_SYMBOL_DIR"] = symbol_dir
vars_obj["GS_FOOTPRINT_DIR"] = footprint_dir
vars_obj["GS_3DMODEL_DIR"] = model_dir
environment["vars"] = vars_obj
data["environment"] = environment

json_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
  else
    echo "Warning: neither jq nor python is available; could not update ${json_file}."
    echo "Set this manually in KiCad -> Preferences -> Configure Paths:"
    echo "  GS_SYMBOL_DIR=${symbol_dir}"
    echo "  GS_FOOTPRINT_DIR=${footprint_dir}"
    echo "  GS_3DMODEL_DIR=${model_dir}"
    return
  fi

  echo "Set KiCad path variables:"
  echo "  GS_SYMBOL_DIR=${symbol_dir}"
  echo "  GS_FOOTPRINT_DIR=${footprint_dir}"
  echo "  GS_3DMODEL_DIR=${model_dir}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config-dir)
      CONFIG_DIR="$2"
      shift 2
      ;;
    --kicad-version)
      KICAD_VERSION="$2"
      CONFIG_DIR="${HOME}/.config/kicad/${KICAD_VERSION}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

SYM_TABLE="${CONFIG_DIR}/sym-lib-table"
FP_TABLE="${CONFIG_DIR}/fp-lib-table"
COMMON_JSON="${CONFIG_DIR}/kicad_common.json"

if [[ ! -d "${REPO_ROOT}/symbols" || ! -d "${REPO_ROOT}/footprints" ]]; then
  echo "Error: script must be run from inside gs-kicad-lib repo." >&2
  exit 1
fi

ensure_table_file "$SYM_TABLE" "(sym_lib_table"
ensure_table_file "$FP_TABLE" "(fp_lib_table"

if [[ ! -f "${SYM_TABLE}.bak" ]]; then
  cp "$SYM_TABLE" "${SYM_TABLE}.bak"
fi
if [[ ! -f "${FP_TABLE}.bak" ]]; then
  cp "$FP_TABLE" "${FP_TABLE}.bak"
fi

while IFS= read -r sym_file; do
  sym_name="$(basename "$sym_file" .kicad_sym)"
  upsert_lib_entry "$SYM_TABLE" "$sym_name" "\${GS_SYMBOL_DIR}/${sym_name}.kicad_sym"
done < <(find "${REPO_ROOT}/symbols" -maxdepth 1 -type f -name '*.kicad_sym' | sort)

while IFS= read -r fp_dir; do
  fp_name="$(basename "$fp_dir" .pretty)"
  upsert_lib_entry "$FP_TABLE" "$fp_name" "\${GS_FOOTPRINT_DIR}/${fp_name}.pretty"
done < <(find "${REPO_ROOT}/footprints" -maxdepth 1 -type d -name '*.pretty' | sort)

update_env_vars_in_common_json "$COMMON_JSON" "$GS_SYMBOL_DIR" "$GS_FOOTPRINT_DIR" "$GS_3DMODEL_DIR"

echo
echo "Setup complete."
echo "KiCad config dir: ${CONFIG_DIR}"
echo "Symbol table: ${SYM_TABLE}"
echo "Footprint table: ${FP_TABLE}"
