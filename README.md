# KiCad Library
Personal KiCad library.

## Quick Setup (Script)

Run from the repository root:

```bash
./scripts/setup-kicad.sh
```

This script will:

- add all `symbols/*.kicad_sym` libraries to KiCad global `sym-lib-table`
- add all `footprints/*.pretty` libraries to KiCad global `fp-lib-table`
- set `GS_SYMBOL_DIR`, `GS_FOOTPRINT_DIR`, and `GS_3DMODEL_DIR` in `kicad_common.json` (using `jq` if available, otherwise Python)
- write symbol/footprint table entries using those variables

By default, the script auto-detects the KiCad config path by OS:

- Linux: `~/.config/kicad/9.0`
- macOS: `~/Library/Preferences/kicad/9.0`
- Windows shells (Git Bash/MSYS/Cygwin): `%APPDATA%/kicad/9.0`

Optional arguments:

```bash
./scripts/setup-kicad.sh --kicad-version 9.0
./scripts/setup-kicad.sh --config-dir /custom/kicad/config/path
```

If neither `jq` nor Python is available, the script will still install symbol/footprint libraries and print instructions to set this manually in KiCad:

- `Preferences -> Configure Paths...`
- `GS_SYMBOL_DIR=/path/to/gs-kicad-lib/symbols`
- `GS_FOOTPRINT_DIR=/path/to/gs-kicad-lib/footprints`
- `GS_3DMODEL_DIR=/path/to/gs-kicad-lib/3d-models`

## Manual Import Into KiCad (v9)

### 1) Clone the repo somewhere stable
Example:

```bash
git clone <repo-url> /home/you/Documents/projects/gs-kicad-lib
```

Use a path that will not move, since KiCad library tables store filesystem paths.

### 2) Add library path variables
In KiCad:

1. Open `Preferences -> Configure Paths...`
2. Add:
   - `GS_SYMBOL_DIR=/home/you/Documents/projects/gs-kicad-lib/symbols`
   - `GS_FOOTPRINT_DIR=/home/you/Documents/projects/gs-kicad-lib/footprints`
   - `GS_3DMODEL_DIR=/home/you/Documents/projects/gs-kicad-lib/3d-models`

`GS_3DMODEL_DIR` is used for custom STEP models. `GS_SYMBOL_DIR` and `GS_FOOTPRINT_DIR` are useful for portable library table paths.

### 3) Add symbol libraries
In KiCad:

1. Open `Preferences -> Manage Symbol Libraries...`
2. Add each file in `symbols/` (`.kicad_sym`) to either:
   - Global libraries (available in all projects), or
   - Project libraries (only current project)

### 4) Add footprint libraries
In KiCad:

1. Open `Preferences -> Manage Footprint Libraries...`
2. Add each `.pretty` directory from `footprints/` as a library.
3. Use library nicknames that match the folder names without `.pretty` (for example `GS_Connectors`, `GS_Resistors`, `GS_Development_Boards`, etc.).

Matching nicknames are important because symbol footprint fields reference libraries like `GS_Connectors:USB-C-SMD`.

## Notes

- Built-in KiCad variables like `KICAD9_3DMODEL_DIR` should already exist; normally you do not need to edit them.
- If a 3D model does not appear, first check that `GS_3DMODEL_DIR` points to this repo's `3d-models/` folder.

## Part Naming + Library Conventions

Use these conventions when adding new parts so symbols, footprints, and BOM exports stay consistent.

### 1) File and library organization

- Symbols go in category libraries: `symbols/GS_<Category>.kicad_sym` (for example `GS_PMIC.kicad_sym`, `GS_Connectors.kicad_sym`).
- Footprints go in matching category libraries: `footprints/GS_<Category>.pretty/<FootprintName>.kicad_mod`.
- 3D models go in `3d-models/` and should have names that clearly map to footprint names.
- Keep symbol `Footprint` properties in the form `<LibraryNickname>:<FootprintName>`, where `<LibraryNickname>` matches the `.pretty` folder name without `.pretty`.

### 2) Symbol naming (the symbol ID)

- Use concise, searchable names with `_` separators.
- For passives/discretes, use:
  - `<Type>_<Package>_<Value>` (examples: `R_0402_10k`, `C_0402_100nF`, `FB_0805_120R`).
- For ICs/modules/connectors, use:
  - primary part number or clear device name (examples: `AP63203WU-7`, `USB_C_Socket`, `ESP32-PICO-KIT-1`).
- If an MPN contains `/`, replace it with `_` in the symbol name (example: `IRM-V838M3-C_TR1`).
- Avoid spaces in symbol names.

### 3) Footprint and 3D naming

- Reuse KiCad standard names for standard packages when possible (for example `R_0402_1005Metric`, `SOIC-8_5.3x5.3mm_P1.27mm`).
- For custom or board-level footprints, use descriptive names:
  - `<VENDOR>_<PART>` or `<DEVICE>_<VARIANT>` (examples: `ADAFRUIT_BNO085`, `ESP32_PICO_1_DEV_KIT`, `USB-C-SMD`).
- Keep footprint names and STEP names semantically aligned so mapping is obvious.

### 4) Symbol fields to include

Required on all symbols:

- `Reference`
- `Value`
- `Footprint`
- `Datasheet` (use `~` or empty when intentionally unavailable)
- `Description`
- `ki_keywords`
- `ki_fp_filters`

Mandatory BOM/procurement fields (except SPICE/simulation-only parts):

- `Manufacturer`
- `Mfr. Part #`
- `LCSC ID`
- `Package`

SPICE/simulation-only parts may omit procurement fields when they are not purchasable physical components.

Field style:

- Keep BOM/procurement fields hidden in symbol graphics (`(hide yes)`).
- Keep field names exactly as shown above (`Mfr. Part #`, `LCSC ID`, etc.) so downstream BOM tooling stays consistent.

### 5) Value field guidance

- For passives: use the electrical value (`10k`, `100nF`, `4.7uF`, `120R @ 100MHz`).
- For semiconductors/ICs: use part number or canonical device value (`AP63203WU-7`, `W25Q128JVSIQ`).
- For virtual/mechanical symbols: use a short functional value (`Logo`, etc.) and set `in_bom no` when appropriate.
