# Contributing

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [KiCad 10](https://www.kicad.org/) — for opening and inspecting symbols/footprints
- **Nix users:** `nix develop` (or `direnv allow`) provides everything needed

## Setup

```bash
git clone <repo-url> ~/Documents/gs-kicad-lib
cd gs-kicad-lib
make install   # registers libraries in KiCad + installs git hooks
uv sync        # installs Python tooling
```

Restart KiCad after `make install`. Libraries appear as `GS_*` in the symbol and footprint choosers.

## Adding a New Part

Run the interactive TUI and follow the prompts:

```bash
uv run kicad-lib
```

<!-- [Screenshot: TUI main menu showing "Import from LCSC" and "Add passive" options] -->

Select **Import from LCSC / EasyEDA**, enter the LCSC part ID, then choose the target symbol library and footprint using the fuzzy-search pickers.

<!-- [Screenshot: fuzzy library picker] -->

For passives (resistors, capacitors, ferrite beads), select **Add passive** instead. The tool derives the symbol from LCSC metadata without needing EasyEDA conversion.

<!-- [Screenshot: passive creator prompts] -->

### Naming conventions

| Part type | Format | Example |
|---|---|---|
| Passives | `<Type>_<Package>_<Value>` | `R_0402_10k`, `C_0603_100nF` |
| ICs / modules | Part number or device name | `AP63203WU-7`, `USB_C_Socket` |

- Replace `/` with `_` in MPNs
- Value field: electrical value for passives (`10k`), part number for ICs (`AP63203WU-7`)
- Procurement fields (Manufacturer, MPN, LCSC ID, Package) must be **hidden** in symbol graphics

## Validation

The validator checks every symbol for required fields and correct visibility:

```bash
make validate
```

This also runs automatically as a pre-push hook, so pushes with invalid symbols are blocked.

## Running Tests

```bash
make unit-test    # pytest
make typecheck    # mypy
make lint         # ruff
```

## Keeping LIBRARIES.md Up to Date

`LIBRARIES.md` is auto-generated from the symbol files. Regenerate it after adding or removing symbols:

```bash
make libraries
git add LIBRARIES.md
git commit -m "docs: update LIBRARIES.md"
```

The pre-push hook will remind you if it's stale, and CI will fail if the committed file doesn't match the symbols on disk.

## Jobset Templates

When starting a new PCB project, copy a jobset template from `templates/jobsets/`:

| Template | Use case |
|---|---|
| `simple-pcb.kicad_jobset` | Standard release (gerbers, BOM, renders, STEP) |
| `jlc-pcba.kicad_jobset` | JLCPCB assembly order with split front/back drawings |
