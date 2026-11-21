from __future__ import annotations

from pathlib import Path

import pytest

from kicad_lib_tools import validation
from kicad_lib_tools.config import LibraryConfig


def test_parse_symbol_file_ignores_unit_suffix_symbols(
    tmp_path: Path,
) -> None:
    symbol_path = tmp_path / "GS_Test.kicad_sym"
    symbol_path.write_text(
        """\
(kicad_symbol_lib
  (symbol "TopLevel"
    (property "Reference" "U" (id 0) (at 0 0 0) (effects (font (size 1.27 1.27))))
  )
  (symbol "TopLevel_1_1"
    (property "Reference" "U" (id 0) (at 0 0 0) (effects (font (size 1.27 1.27))))
  )
)
""",
        encoding="utf-8",
    )
    symbols = validation.parse_symbol_file(symbol_path)
    assert [symbol.name for symbol in symbols] == ["TopLevel"]


def test_expand_paths_deduplicates_repo_relative_entries(
    repo: LibraryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symbol_dir = repo.symbol_path
    symbol_path = symbol_dir / "GS_Test.kicad_sym"
    symbol_path.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    monkeypatch.chdir(repo.repo_root)

    paths = validation.expand_paths(
        [str(symbol_dir), str(symbol_path), "symbols/GS_Test.kicad_sym"]
    )
    assert paths == [symbol_path]


def test_main_reports_warning_only_symbols_as_success(
    capsys,
    tmp_path: Path,
) -> None:
    symbol_path = tmp_path / "GS_Test.kicad_sym"
    symbol_path.write_text(
        """\
(kicad_symbol_lib
  (symbol "WarnOnly"
    (in_bom yes)
    (property "Reference" "U" (id 0) (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Value" "WarnOnly" (id 1) (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "GS_SO:SOT-23" (id 2) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
    (property "Datasheet" "~" (id 3) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
    (property "Description" "test" (id 4) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
    (property "Manufacturer" "Test" (id 5) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
    (property "MPN" "TEST-1" (id 6) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
    (property "LCSC ID" "C1" (id 7) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
    (property "Package" "SOT-23" (id 8) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
  )
)
""",
        encoding="utf-8",
    )

    assert validation.main([str(symbol_path)]) == 0
    captured = capsys.readouterr()
    assert "Symbol field validation passed with warnings" in captured.out
    assert "GS_Test:WarnOnly" in captured.out
    assert "no SPICE model configured" in captured.out


def test_main_reports_qualified_symbol_names_for_failures(
    capsys,
    tmp_path: Path,
) -> None:
    symbol_path = tmp_path / "GS_Test.kicad_sym"
    symbol_path.write_text(
        """\
(kicad_symbol_lib
  (symbol "BrokenPart"
    (in_bom yes)
    (property "Reference" "U" (id 0) (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Value" "BrokenPart" (id 1) (at 0 0 0) (effects (font (size 1.27 1.27))))
  )
)
""",
        encoding="utf-8",
    )

    assert validation.main([str(symbol_path)]) == 1
    captured = capsys.readouterr()
    assert "Symbol field validation failed" in captured.out
    assert "GS_Test:BrokenPart" in captured.out
    assert "missing required fields: Footprint, Datasheet, Description" in captured.out
