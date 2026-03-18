from __future__ import annotations

from pathlib import Path

import pytest

from scripts.easyeda_import.symbols import prepare_symbol_block, render_symbol_library_update
from scripts.easyeda_import.footprints import rewrite_model_paths


def assert_matches_reference(
    *,
    actual: str,
    relative_path: str,
    reference_dir: Path,
    create_reference: bool,
) -> None:
    reference_path = reference_dir / relative_path
    if create_reference:
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        reference_path.write_text(actual, encoding="utf-8")
        pytest.skip(f"Created reference file: {reference_path}")
    assert reference_path.read_text(encoding="utf-8") == actual


def test_prepare_symbol_block_regression(
    reference_dir: Path,
    create_reference: bool,
) -> None:
    symbol_text = """\
(symbol "TPS5430DDAR"
  (property "Reference" "U" (id 0) (at 0 7.62 0) (effects (font (size 1.27 1.27))))
  (property "Value" "TPS5430DDAR" (id 1) (at 0 0 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "easyeda2kicad:SOIC-8_5.3x5.3mm_P1.27mm" (id 2) (at 0 -2.54 0) (effects (font (size 1.27 1.27)) hide))
  (property "Datasheet" "https://www.lcsc.com/datasheet/C3235552.pdf" (id 3) (at 0 -5.08 0) (effects (font (size 1.27 1.27)) hide))
  (property "LCSC Part" "C3235552" (id 6) (at 0 -7.62 0) (effects (font (size 1.27 1.27)) hide))
)
"""
    actual = prepare_symbol_block(
        symbol_block=symbol_text,
        footprint_ref="GS_SO:SOIC-8_5.3x5.3mm_P1.27mm",
        datasheet="https://www.lcsc.com/datasheet/C3235552.pdf",
        description="Buck regulator",
        manufacturer="Texas Instruments",
        mpn="TPS5430DDAR",
        lcsc_id="C3235552",
        package="SOIC-8_5.3x5.3mm_P1.27mm",
        validation_override="",
        spice_warning_override="",
    )
    assert_matches_reference(
        actual=actual,
        relative_path="easyeda_import/prepared_symbol.kicad_sym",
        reference_dir=reference_dir,
        create_reference=create_reference,
    )


def test_rewrite_model_paths_regression(
    reference_dir: Path,
    create_reference: bool,
) -> None:
    footprint_text = """\
(footprint "Test:Part"
  (model "/tmp/generated.step"
    (offset (xyz 0 0 0))
    (scale (xyz 1 1 1))
  )
  (model "/tmp/generated.wrl"
    (offset (xyz 1 2 3))
    (scale (xyz 1 1 1))
  )
  (fp_text value "Part" (at 0 0 0))
)
"""
    actual = rewrite_model_paths(
        footprint_text,
        [
            "${GS_3DMODEL_DIR}/bucket/generated.step",
            "${GS_3DMODEL_DIR}/bucket/generated.wrl",
        ],
    )
    assert_matches_reference(
        actual=actual,
        relative_path="easyeda_import/rewritten_footprint.kicad_mod",
        reference_dir=reference_dir,
        create_reference=create_reference,
    )


def test_render_symbol_library_update_regression(
    reference_dir: Path,
    create_reference: bool,
    tmp_path: Path,
) -> None:
    symbol_library_path = tmp_path / "GS_Test.kicad_sym"
    symbol_library_path.write_text(
        """\
(kicad_symbol_lib
  (version 20241209)
  (generator "kicad_symbol_editor")
)
""",
        encoding="utf-8",
    )
    symbol_block = """\
  (symbol "TPS5430DDAR"
    (property "Reference" "U" (id 0) (at 0 7.62 0) (effects (font (size 1.27 1.27))))
  )
"""
    actual = render_symbol_library_update(
        symbol_library_path=symbol_library_path,
        symbol_name="TPS5430DDAR",
        symbol_block=symbol_block,
        overwrite=False,
    )
    assert_matches_reference(
        actual=actual,
        relative_path="easyeda_import/rendered_symbol_library.kicad_sym",
        reference_dir=reference_dir,
        create_reference=create_reference,
    )
