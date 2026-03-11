# KiCad Library

Personal KiCad library.

## Quick Setup

Run from the repository root:

```bash
./scripts/setup-kicad.sh
```

This script will:

- add all `symbols/*.kicad_sym` libraries to KiCad global `sym-lib-table`
- add all `footprints/*.pretty` libraries to KiCad global `fp-lib-table`
- set `GS_SYMBOL_DIR`, `GS_FOOTPRINT_DIR`, and `GS_3DMODEL_DIR` in
  `kicad_common.json`
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

Optional git hooks:

```bash
./scripts/install-git-hooks.sh
```

This configures the repo-managed `pre-push` hook to validate all `.kicad_sym`
files in the repo against the required symbol fields in this README.

If neither `jq` nor Python is available, the script will still install
symbol/footprint libraries and print instructions to set this manually in KiCad:

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

Use a path that will not move, since KiCad library tables store filesystem
paths.

### 2) Add library path variables

In KiCad:

1. Open `Preferences -> Configure Paths...`
2. Add:
   - `GS_SYMBOL_DIR=/home/you/Documents/projects/gs-kicad-lib/symbols`
   - `GS_FOOTPRINT_DIR=/home/you/Documents/projects/gs-kicad-lib/footprints`
   - `GS_3DMODEL_DIR=/home/you/Documents/projects/gs-kicad-lib/3d-models`

`GS_3DMODEL_DIR` is used for custom STEP models. `GS_SYMBOL_DIR` and
`GS_FOOTPRINT_DIR` are useful for portable library table paths.

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
3. Use library nicknames that match the folder names without `.pretty` (for
   example `GS_Connectors`, `GS_Resistors`, `GS_Development_Boards`, etc.).

Matching nicknames are important because symbol footprint fields reference
libraries like `GS_Connectors:USB-C-SMD`.

## Jobset Templates (KiCad v9)

Default jobset:

- `templates/jobsets/simple-pcb.kicad_jobset`

Use this as the starting point for normal PCB release output. It is intended to
generate common manufacturing and documentation artifacts into project folders:

- `production/` (including `${PROJECTNAME}-gerbers.zip`)
- `drawings/`
- `images/`
- `3d-model/`

The default jobset includes:

- schematic PDF export
- PCB drawing PDF export
- Gerber + drill export
- BOM CSV export
- board renders (`front`, `back`, `orthographic`)
- STEP 3D export

Alternate template:

- `templates/jobsets/jlc-pcba.kicad_jobset`

Use `jlc-pcba` when you want the JLC-flavored drawing split (front and back PCB
PDFs) instead of the single combined PCB drawing PDF used by `simple-pcb`.

## Notes

- Built-in KiCad variables like `KICAD9_3DMODEL_DIR` should already exist;
  normally you do not need to edit them.
- If a 3D model does not appear, first check that `GS_3DMODEL_DIR` points to
  this repo's `3d-models/` folder.

## EasyEDA Import Wrapper

This repo includes a repo-aware importer at:

```bash
python3 scripts/easyeda-import.py
```

It is intended to sit on top of your `easyeda2kicad` fork and automate the
repo-specific work that the generic converter should not own:

- staging converter output under `tmp/easyeda-import/`
- importing symbols into `symbols/GS_<Category>.kicad_sym`
- importing footprints into `footprints/GS_<Category>.pretty/`
- moving 3D models into `3d-models/`
- rewriting footprint model paths to use `GS_3DMODEL_DIR`
- normalizing symbol procurement fields to this repo's conventions
- validating imported symbols with `scripts/check-symbol-fields.py`

Example:

```bash
python3 scripts/easyeda-import.py \
  --lcsc-id C123456 \
  --symbol-lib GS_IC \
  --footprint-lib GS_SO \
  --mfr-part TPS5430DDAR \
  --package SOIC-8_5.3x5.3mm_P1.27mm
```

If run in a terminal without all required flags, the script prompts for missing
repo-specific values. The interactive flow now uses fuzzy terminal selectors
for symbol libraries, footprint libraries, and existing-footprint linking:

- type to filter results
- arrow keys to move through the list
- one option per bullet line
- a short visible list that scrolls as needed
- a final summary and confirmation before repo files are changed

Interactive mode also lets you:

- choose whether to import the symbol
- choose whether to import the generated footprint
- choose whether to import 3D models
- link an imported symbol to the generated footprint
- link an imported symbol to an existing repo footprint
- leave an imported symbol with no footprint link

### Converter command

By default, the wrapper tries to run the sibling fork checkout at:

```bash
../easyeda2kicad.py/.venv/bin/python -m easyeda2kicad
```

You can override that with either:

```bash
python3 scripts/easyeda-import.py --converter-command "easyeda2kicad"
```

or:

```bash
GS_EASYEDA2KICAD_CMD="easyeda2kicad" python3 scripts/easyeda-import.py ...
```

The fuzzy interactive selectors require `prompt_toolkit` at runtime. The
non-interactive CLI continues to work without it.

### Import mode flags

For scripting or non-interactive use, the importer now supports:

```bash
python3 scripts/easyeda-import.py \
  --lcsc-id C123456 \
  --symbol-lib GS_IC \
  --no-footprint \
  --no-3d \
  --footprint-link-mode existing \
  --existing-footprint-lib GS_SO \
  --existing-footprint SOIC-8_5.3x5.3mm_P1.27mm \
  --mfr-part TPS5430DDAR \
  --package SOIC-8_5.3x5.3mm_P1.27mm
```

Useful flags:

- `--no-symbol`
- `--no-footprint`
- `--no-3d`
- `--footprint-link-mode generated|existing|none`
- `--existing-footprint-lib`
- `--existing-footprint`

### New libraries

If you target a symbol or footprint library that does not exist yet, the script
asks before creating it. When new libraries are created, the wrapper offers to
run `./scripts/setup-kicad.sh` so KiCad can pick up the new library entries.

## Part Naming + Library Conventions

Use these conventions when adding new parts so symbols, footprints, and BOM
exports stay consistent.

### 1) File and library organization

- Symbols go in category libraries: `symbols/GS_<Category>.kicad_sym` (for
  example `GS_PMIC.kicad_sym`, `GS_Connectors.kicad_sym`).
- Footprints go in matching category libraries:
  `footprints/GS_<Category>.pretty/<FootprintName>.kicad_mod`.
- 3D models go in `3d-models/` and should have names that clearly map to
  footprint names.
- Keep symbol `Footprint` properties in the form
  `<LibraryNickname>:<FootprintName>`, where `<LibraryNickname>` matches the
  `.pretty` folder name without `.pretty`.

### 2) Symbol naming (the symbol ID)

- Use concise, searchable names with `_` separators.
- For passives/discretes, use:
  - `<Type>_<Package>_<Value>` (examples: `R_0402_10k`, `C_0402_100nF`,
    `FB_0805_120R`).
- For ICs/modules/connectors, use:
  - primary part number or clear device name (examples: `AP63203WU-7`,
    `USB_C_Socket`, `ESP32-PICO-KIT-1`).
- If an MPN contains `/`, replace it with `_` in the symbol name (example:
  `IRM-V838M3-C_TR1`).
- Avoid spaces in symbol names.

### 3) Footprint and 3D naming

- Reuse KiCad standard names for standard packages when possible (for example
  `R_0402_1005Metric`, `SOIC-8_5.3x5.3mm_P1.27mm`).
- For custom or board-level footprints, use descriptive names:
  - `<VENDOR>_<PART>` or `<DEVICE>_<VARIANT>` (examples: `ADAFRUIT_BNO085`,
    `ESP32_PICO_1_DEV_KIT`, `USB-C-SMD`).
- Keep footprint names and STEP names semantically aligned so mapping is
  obvious.

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

SPICE/simulation-only parts may omit procurement fields when they are not
purchasable physical components.

Symbols that intentionally do not follow this schema may instead include a
hidden `Field Validation Override` property with a short reason. The validator
will treat that as an explicit opt-out.

Symbols without simulation properties will trigger a non-fatal warning about
missing SPICE configuration. If that warning is intentional, add a hidden
`SPICE Warning Override` property with a short reason.

Field style:

- Keep BOM/procurement fields hidden in symbol graphics (`(hide yes)`).
- Keep field names exactly as shown above (`Mfr. Part #`, `LCSC ID`, etc.) so
  downstream BOM tooling stays consistent.
- Keep `Field Validation Override` hidden too, when used.
- Keep `SPICE Warning Override` hidden too, when used.

### 5) Value field guidance

- For passives: use the electrical value (`10k`, `100nF`, `4.7uF`,
  `120R @ 100MHz`).
- For semiconductors/ICs: use part number or canonical device value
  (`AP63203WU-7`, `W25Q128JVSIQ`).
- For virtual/mechanical symbols: use a short functional value (`Logo`, etc.)
  and set `in_bom no` when appropriate.

## Validation

Preferred entry point:

```bash
make validate
```

This runs the repo-wide symbol-field validation.

Run the validator manually:

```bash
python3 scripts/check-symbol-fields.py
```

With no arguments, it validates the repository's `symbols/` directory regardless of
your current working directory.

To validate only specific files:

```bash
python3 scripts/check-symbol-fields.py symbols/GS_PMIC.kicad_sym
```

The validator checks that required fields exist, that procurement fields on BOM
parts use the exact README field names, and that those procurement fields are
hidden. If a symbol has a hidden `Field Validation Override` property with a
non-empty reason, the validator skips the normal field checks for that symbol.
Invalid field names such as `LCSC Part` still fail even when an override is
present.
