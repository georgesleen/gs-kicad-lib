# KiCad Library

[![Validate Symbol Fields](https://github.com/georgesleen/gs-kicad-lib/actions/workflows/validate-symbol-fields.yml/badge.svg)](https://github.com/georgesleen/gs-kicad-lib/actions/workflows/validate-symbol-fields.yml)

Personal KiCad component library. [partsmith](https://github.com/georgesleen/kicad-partsmith)
imports, names, and validates its parts; `partsmith.toml` holds this library's settings.
See [LIBRARIES.md](LIBRARIES.md) for a full list of components, and [CONTRIBUTING.md](CONTRIBUTING.md) to add new ones.

## Setup

```bash
git clone <repo-url> ~/Documents/gs-kicad-lib
cd gs-kicad-lib
make install   # installs git hooks, registers libraries + path vars in KiCad 10
```

Restart KiCad. Libraries appear as `GS_*` in the symbol/footprint choosers.

**Nix:** `nix develop` (or `direnv allow`) provides `uv` and `make`. `uv` installs partsmith from
the pinned commit in `uv.lock`.

## Commands

| Command | What it does |
|---|---|
| `make run` | Open the partsmith menu (import or add a passive) |
| `make import` | Import a part from LCSC/EasyEDA (skips menu) |
| `make passive` | Add a derived passive symbol (skips menu) |
| `make libraries` | Regenerate LIBRARIES.md |
| `make validate` | Validate all symbol fields |
| `make install` | Install git hooks and re-run `partsmith setup` |
| `make update-tools` | Update partsmith to its latest commit |

`uv run partsmith --help` lists every partsmith command. The
[partsmith README](https://github.com/georgesleen/kicad-partsmith#readme) describes the import
review step, the non-interactive flags, and the `partsmith.toml` settings.

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

If `partsmith setup` cannot run, configure manually in KiCad:

**`Preferences → Configure Paths`:**
```
GS_SYMBOL_DIR      = /path/to/gs-kicad-lib/symbols
GS_FOOTPRINT_DIR   = /path/to/gs-kicad-lib/footprints
GS_3DMODEL_DIR     = /path/to/gs-kicad-lib/3d-models
GS_SPICE_MODEL_DIR = /path/to/gs-kicad-lib/spice-models
```

**`Preferences → Manage Symbol Libraries`:** add each `symbols/*.kicad_sym`.

**`Preferences → Manage Footprint Libraries`:** add each `footprints/*.pretty` with nicknames matching the folder name (without `.pretty`).
