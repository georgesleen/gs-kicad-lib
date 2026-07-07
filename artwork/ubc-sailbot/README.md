# UBC Sailbot logo

`generate.py` rebuilds the `UBC_Sailbot_Logo` footprints as vector geometry
measured from `ubc-sailbot.png` (nothing is traced). Layers: sails on
F.SilkS, binary digits on F.Cu under the silk (subtle emboss under the
soldermask), "UBC SAILBOT" as F.Cu plus a matching F.Mask opening (exposed
metal text), and an F.Cu rule area keeping pours, tracks, and vias out of
the artwork. The binary is "UBC SAILBOT " in 8-bit ASCII.

Regenerate in place:

```bash
uv run generate.py ../../footprints/GS_Virtual.pretty
```

Add `--svg` to also write SVG previews to the output directory. Fonts are
resolved through fontconfig: TeX Gyre Heros Bold (text) and Liberation Mono
Bold (digits) must be installed. Output is deterministic (uuid5), so an
unchanged regeneration produces no diff.
