from __future__ import annotations

import pytest

from kicad_lib_tools.selectors import (
    SelectionOption,
    fuzzy_positions,
    highlight,
    match_options,
    preview_lines,
    visible_range,
)


@pytest.mark.parametrize(
    ("selected", "count", "expected"),
    [
        (0, 3, (0, 3)),
        (0, 20, (0, 8)),
        (10, 20, (6, 14)),
        (19, 20, (12, 20)),
    ],
)
def test_visible_range_keeps_selection_in_window(
    selected: int, count: int, expected: tuple[int, int]
) -> None:
    assert visible_range(selected, count, max_visible=8) == expected


def test_preview_lines_returns_short_lists_unchanged() -> None:
    assert preview_lines(["a", "b"], height=3) == ["a", "b"]


def test_preview_lines_counts_hidden_lines() -> None:
    assert preview_lines(["a", "b", "c", "d"], height=3) == ["a", "b", "... 2 more"]


LIBRARIES = [
    SelectionOption("GS_Connectors", "GS_Connectors"),
    SelectionOption("GS_Optoelectronic", "GS_Optoelectronic"),
    SelectionOption("GS_IC", "GS_IC"),
]
CONTENTS = {
    "GS_Connectors": ["S2B-XH-A-1", "USB_C_Socket_PowerOnly", "USB_C_Socket_SS"],
    "GS_Optoelectronic": ["LED_0402_Green"],
    "GS_IC": ["USBLC6-2P6"],
}


def contents(option: SelectionOption) -> list[str]:
    return CONTENTS[option.value]


def test_fuzzy_positions_finds_ordered_characters_ignoring_case() -> None:
    assert fuzzy_positions("con", "GS_Connectors") == (3, 4, 5)
    assert fuzzy_positions("xyz", "GS_Connectors") is None


def test_match_options_returns_everything_for_a_blank_query() -> None:
    assert [match.option.value for match in match_options(LIBRARIES, "  ")] == [
        "GS_Connectors",
        "GS_Optoelectronic",
        "GS_IC",
    ]


def test_match_options_finds_libraries_by_contents_after_label_matches() -> None:
    matches = match_options(LIBRARIES, "usb", contents)
    assert [match.option.value for match in matches] == ["GS_Connectors", "GS_IC"]
    assert matches[0].content_hits == ("USB_C_Socket_PowerOnly", "USB_C_Socket_SS")
    assert matches[0].label_positions == ()


def test_match_options_ranks_label_matches_first() -> None:
    matches = match_options(LIBRARIES, "ic", contents)
    assert matches[0].option.value == "GS_IC"
    assert matches[0].label_positions == (3, 4)


def test_match_options_returns_nothing_without_a_match() -> None:
    assert match_options(LIBRARIES, "qqq", contents) == []


def test_highlight_marks_matched_characters() -> None:
    assert highlight("GS_IC", (3, 4), "class:selected") == [
        ("class:selected", "G"),
        ("class:selected", "S"),
        ("class:selected", "_"),
        ("class:selected class:match", "I"),
        ("class:selected class:match", "C"),
    ]
