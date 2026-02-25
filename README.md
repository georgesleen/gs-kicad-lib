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
