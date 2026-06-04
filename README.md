# KiCad Library

Personal KiCad component library with tooling to import from LCSC/EasyEDA.

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
| `uv run kicad-lib-import` | Import a part from LCSC/EasyEDA |
| `uv run kicad-lib-passive` | Add a derived passive symbol |
| `uv run kicad-lib-run` | Open the interactive menu |
| `make validate` | Validate all symbol fields |
| `make unit-test` | Run the test suite |
| `make typecheck` | Run mypy |
| `make install` | Re-run setup + install git hooks |

## Importing Parts

```bash
uv run kicad-lib-import --lcsc-id C123456
```

Prompts for missing values interactively. Non-interactive example:

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
