# UBC Sailbot logo

`generate.py` rebuilds the `UBC_Sailbot_Logo` footprints as vector geometry
measured from `ubc-sailbot.png` (nothing is traced). Layers: sails on
F.SilkS, binary digits on F.Cu under the silk (subtle emboss under the
soldermask), "UBC SAILBOT" as F.Cu plus a matching F.Mask opening (exposed
metal text), and an F.Cu rule area keeping pours, tracks, and vias out of
the artwork. The binary is "UBC SAILBOT " in 8-bit ASCII.

Variants written by one run:

- `UBC_Sailbot_Logo` (10mm) and `_Small` (6mm): the main logo above.
- `_Alt`: "UBC SAILBOT" normalized to one line under the sails instead of
  cut out of the big sail.
- `_Plain`: silkscreen only, white sails and white text, no copper or mask.
- `_Large` (15mm): large white silk sails with the binary texture embossed
  in copper under the silk; no text, no exposed copper.
- `_Huge` (40mm): silkscreen sails only, no copper, no text.

Badge variants sit on a filleted plate with equal margins around the
artwork, "UBC"/"SAILBOT" right-justified to the left of the sails (`_Line`
puts both words on one line):

- `_Enig` / `_Enig_Line`: white silk plate, gold (copper + mask) sails and
  text.
- `_Enig_Num`: as `_Enig`, plus binary numbers on the small sail formed by a
  mask opening with no copper, so they read as bare board inside the gold.
- `_Silk` / `_Silk_Line`: the plate is a mask opening (exposed board), the
  sails and text are white silk, and copper binary numbers are embossed under
  the small-sail silk (no exposed copper).

Regenerate in place:

```bash
uv run generate.py ../../footprints/GS_Virtual.pretty
```

Add `--svg` to also write SVG previews to the output directory. Fonts are
resolved through fontconfig: TeX Gyre Heros Bold (text) and Liberation Mono
Bold (digits) must be installed. Output is deterministic (uuid5), so an
unchanged regeneration produces no diff.
