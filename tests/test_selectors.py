from __future__ import annotations

import pytest

from kicad_lib_tools.selectors import preview_lines, visible_range


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
