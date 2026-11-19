# KiCad Library

[![Validate Symbol Fields](https://github.com/georgesleen/gs-kicad-lib/actions/workflows/validate-symbol-fields.yml/badge.svg)](https://github.com/georgesleen/gs-kicad-lib/actions/workflows/validate-symbol-fields.yml)
[![Python Checks](https://github.com/georgesleen/gs-kicad-lib/actions/workflows/python-checks.yml/badge.svg)](https://github.com/georgesleen/gs-kicad-lib/actions/workflows/python-checks.yml)

Personal KiCad component library with tooling to import from LCSC/EasyEDA.
See [LIBRARIES.md](LIBRARIES.md) for a full list of components, and [CONTRIBUTING.md](CONTRIBUTING.md) to add new ones.

## Setup

```bash
git clone <repo-url> ~/Documents/gs-kicad-lib
cd gs-kicad-lib
python3 scripts/setup-kicad.py  # registers libraries + path vars in KiCad 10
uv sync                          # installs Python tooling
```

Restart KiCad. Libraries appear as `GS_*` in the symbol/footprint choosers.

**Nix:** `nix develop` (or `direnv allow`) provides `uv`, `python3.13`, and `make`.

The script auto-detects the KiCad config directory:

| OS | Default path |
|---|---|
| Linux | `~/.config/kicad/10.0` |
| macOS | `~/Library/Preferences/kicad/10.0` |
| Windows | `%APPDATA%\kicad\10.0` |

Override: `python3 scripts/setup-kicad.py --config-dir /path/to/kicad/10.0`

## Commands

| Command | What it does |
|---|---|
| `uv run kicad-lib` | Open the interactive TUI menu (recommended entry point) |
| `uv run kicad-lib-import` | Import a part from LCSC/EasyEDA (skips menu) |
| `uv run kicad-lib-passive` | Add a derived passive symbol (skips menu) |
| `make libraries` | Regenerate LIBRARIES.md |
| `make validate` | Validate all symbol fields |
| `make unit-test` | Run the test suite |
| `make typecheck` | Run mypy |
| `make lint` | Run ruff check + format check |
| `make format` | Auto-format with ruff |
| `make install` | Re-run setup + install git hooks |

## Importing Parts

```bash
uv run kicad-lib
```

The TUI walks through selecting the workflow (import from LCSC or add a passive), prompts for an LCSC ID, and handles library/footprint selection with fuzzy search.

**Shortcuts** — jump directly to a workflow without the menu:

```bash
uv run kicad-lib-import   # import a part from LCSC/EasyEDA
uv run kicad-lib-passive  # add a derived passive symbol
```

### Review step

After an interactive import writes the part, the importer opens it in KiCad and waits until you close the editors:

- The symbol is placed on a scratch schematic in `eeschema`. Click it and press **Ctrl+Shift+E** to edit the library copy.
- The footprint opens in the footprint editor, detached from its library. To keep edits, save it over the same file.

The importer then validates the symbol and asks whether to keep the import. A revert removes only the imported symbol and the files the import wrote; other edits to the same libraries stay. A revert does not delete a library that the import created. Pass `--no-review` to skip this step.

### Non-interactive import

For scripting or automation, pass all flags directly:

```bash
uv run kicad-lib-import \
  --lcsc-id C123456 \
  --symbol-lib GS_IC \
  --footprint-lib GS_SO \
  --mpn TPS5430DDAR \
  --package SOIC-8_5.3x5.3mm_P1.27mm
```

Key flags: `--no-symbol`, `--no-footprint`, `--no-3d`,
`--footprint-link-mode generated|existing|none`,
`--converter-command /path/to/easyeda2kicad`

`--footprint-link-mode` picks the footprint source: `generated` imports the EasyEDA footprint and links
the symbol to it. 3D models import only with the EasyEDA footprint.

When new libraries are created, the importer offers to re-run `setup-kicad.py`.

## Conventions

### Symbol naming

- Passives: `<Type>_<Package>_<Value>` — `R_0402_10k`, `C_0603_100nF`, `FB_0805_120R`
- ICs/connectors: part number or device name — `AP63203WU-7`, `USB_C_Socket`
- Replace `/` with `_` in MPNs

### Value field

- Passives: electrical value — `10k`, `100nF`
- ICs: part number — `AP63203WU-7`

### Required fields (all symbols)

`Reference`, `Value`, `Footprint`, `Datasheet`, `Description`, `ki_keywords`, `ki_fp_filters`

### Procurement fields (BOM parts, must be hidden)

`Manufacturer`, `MPN`, `LCSC ID`, `Package`

Add a hidden `Field Validation Override` property to opt a symbol out of field checks.
Add a hidden `SPICE Warning Override` to suppress missing-SPICE-config warnings.

## Jobset Templates

- `templates/jobsets/simple-pcb.kicad_jobset` — standard release (gerbers, BOM, renders, STEP)
- `templates/jobsets/jlc-pcba.kicad_jobset` — JLC variant with split front/back PCB drawings

## Manual KiCad Setup

If `setup-kicad.py` cannot run, configure manually in KiCad:

**`Preferences → Configure Paths`:**
```
GS_SYMBOL_DIR      = /path/to/gs-kicad-lib/symbols
GS_FOOTPRINT_DIR   = /path/to/gs-kicad-lib/footprints
GS_3DMODEL_DIR     = /path/to/gs-kicad-lib/3d-models
GS_SPICE_MODEL_DIR = /path/to/gs-kicad-lib/spice-models
```

**`Preferences → Manage Symbol Libraries`:** add each `symbols/*.kicad_sym`.

**`Preferences → Manage Footprint Libraries`:** add each `footprints/*.pretty` with nicknames matching the folder name (without `.pretty`).
