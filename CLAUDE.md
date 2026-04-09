# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make install      # Install git hooks and register libraries with KiCad
make import       # Interactively import a part from LCSC via EasyEDA
make passive      # Add a derived passive symbol using an LCSC ID
make validate     # Validate all symbol fields against style guide
make unit-test    # Run the test suite (uv run pytest)
```

Run a single test file: `uv run pytest tests/test_check_symbol_fields.py`

The pre-push git hook runs `make validate` automatically.

## Architecture

This is a personal KiCad component library with tooling to import parts from LCSC/EasyEDA and validate them.

**Library files** live in `symbols/` (`.kicad_sym`), `footprints/` (`.pretty/` dirs), `3d-models/`, and `spice-models/`. All libraries are prefixed `GS_` and categorized by component type or function.

**Import pipeline** (`scripts/easyeda_import/`): `make import` runs an interactive CLI that downloads a part from EasyEDA, stages it to `tmp/easyeda-import/`, normalizes fields to repo conventions, links 3D models with `GS_3DMODEL_DIR`-relative paths, and writes the result into the appropriate `GS_<Category>` library. Key modules:
- `importer.py` — orchestrates the full import workflow
- `symbols.py` — field normalization logic
- `selectors.py` — fuzzy terminal UI for choosing target library/footprint
- `passive_creator.py` — creates derived passive symbols from LCSC data (no easyeda2kicad needed)
- `lcsc_api.py` — fetches part metadata directly from LCSC product API

**Validator** (`scripts/check-symbol-fields.py`): checks every symbol for required fields (Reference, Value, Footprint, Datasheet, Description) and, on BOM parts, procurement fields (Manufacturer, MPN, LCSC ID, Package — all must be hidden). A symbol can opt out via `Field Validation Override` property.

## Symbol Naming & Field Conventions

- Passives: `<Type>_<Package>_<Value>` — e.g., `R_0402_10k`, `C_0603_100nF`
- ICs/modules/connectors: part number or device name — e.g., `AP63203WU-7`, `USB_C_Socket`
- Replace `/` with `_` in MPNs
- Value field: electrical value for passives (`10k`, `100nF`), part number for ICs
- Procurement fields (Manufacturer, MPN, LCSC ID, Package) must be **hidden** in symbol graphics
