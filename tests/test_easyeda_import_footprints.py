from __future__ import annotations

from pathlib import Path

import pytest

from scripts.easyeda_import.errors import ImportErrorWithExitCode
from scripts.easyeda_import.footprints import parse_footprint_name, rewrite_model_paths


def test_parse_footprint_name_parses_kicad_v6_footprint_name(tmp_path: Path) -> None:
    footprint_path = tmp_path / "part.kicad_mod"
    footprint_path.write_text('(footprint "MyLib:USB_C_Receptacle"\n)\n', encoding="utf-8")
    assert parse_footprint_name(footprint_path) == "USB_C_Receptacle"


def test_parse_footprint_name_parses_legacy_module_name(tmp_path: Path) -> None:
    footprint_path = tmp_path / "part.kicad_mod"
    footprint_path.write_text(
        "(module easyeda2kicad:SOT-363_L2.0-W1.3-P0.65-LS2.1-BR (layer F.Cu)\n)\n",
        encoding="utf-8",
    )
    assert parse_footprint_name(footprint_path) == "SOT-363_L2.0-W1.3-P0.65-LS2.1-BR"


def test_parse_footprint_name_raises_for_missing_header(tmp_path: Path) -> None:
    footprint_path = tmp_path / "part.kicad_mod"
    footprint_path.write_text("(fp_text reference REF**)\n", encoding="utf-8")
    with pytest.raises(ImportErrorWithExitCode, match="failed to parse footprint name"):
        parse_footprint_name(footprint_path)


def test_rewrite_model_paths_drops_staged_models_when_no_repo_paths() -> None:
    footprint_text = """\
(footprint "Test:Part"
  (model "/tmp/generated.step"
    (offset (xyz 0 0 0))
  )
  (fp_text value "Part" (at 0 0 0))
)
"""
    assert rewrite_model_paths(footprint_text, []) == (
        '(footprint "Test:Part"\n'
        '  (fp_text value "Part" (at 0 0 0))\n'
        ')\n'
    )


def test_rewrite_model_paths_replaces_each_model_reference() -> None:
    footprint_text = """\
(footprint "Test:Part"
  (model "/tmp/generated.step"
    (offset (xyz 0 0 0))
  )
  (model "/tmp/generated.wrl"
    (offset (xyz 1 2 3))
  )
)
"""
    rewritten = rewrite_model_paths(
        footprint_text,
        [
            "${GS_3DMODEL_DIR}/generated.step",
            "${GS_3DMODEL_DIR}/generated.wrl",
        ],
    )
    assert "${GS_3DMODEL_DIR}/generated.step" in rewritten
    assert "${GS_3DMODEL_DIR}/generated.wrl" in rewritten
