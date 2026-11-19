from __future__ import annotations

from pathlib import Path

import pytest

from kicad_lib_tools.categories import (
    library_for_categories,
    load_category_libraries,
    record_category_library,
    render_category_libraries,
)
from kicad_lib_tools.errors import ImportErrorWithExitCode


def test_render_and_load_round_trip_quoted_categories(tmp_path: Path) -> None:
    table = {'Odd "quoted" \\ name': "GS_IC", "Diodes": "GS_Diodes"}
    path = tmp_path / "categories.toml"
    path.write_text(render_category_libraries(table), encoding="utf-8")
    assert load_category_libraries(path) == table


def test_render_sorts_categories_case_insensitively() -> None:
    text = render_category_libraries({"zener": "GS_Diodes", "Inductors": "GS_Inductors"})
    assert text.index('"Inductors"') < text.index('"zener"')


def test_load_returns_empty_table_without_file(tmp_path: Path) -> None:
    assert load_category_libraries(tmp_path / "missing.toml") == {}


def test_load_rejects_non_string_libraries(tmp_path: Path) -> None:
    path = tmp_path / "categories.toml"
    path.write_text('"Diodes" = 3\n', encoding="utf-8")
    with pytest.raises(ImportErrorWithExitCode, match="must map to a library name"):
        load_category_libraries(path)


def test_library_for_categories_prefers_the_first_mapped_category() -> None:
    table = {"Connectors": "GS_Connectors", "USB Connectors": "GS_USB"}
    assert library_for_categories(table, ["USB Connectors", "Connectors"]) == "GS_USB"
    assert library_for_categories(table, ["Pin Headers", "Connectors"]) == "GS_Connectors"
    assert library_for_categories(table, ["Pin Headers"]) is None


def test_record_adds_new_categories_only(tmp_path: Path) -> None:
    path = tmp_path / "categories.toml"
    assert record_category_library(path, "Diodes", "GS_Diodes")
    assert not record_category_library(path, "Diodes", "GS_Other")
    assert not record_category_library(path, "", "GS_Other")
    assert load_category_libraries(path) == {"Diodes": "GS_Diodes"}
