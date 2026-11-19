from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import ImportErrorWithExitCode

# prompt_toolkit is a runtime dep that may be absent; pre-annotate as Any so
# both the import and the None fallback are valid under mypy strict.
Application: Any = None
try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.styles import Style
except ImportError:  # pragma: no cover - runtime dependency only
    pass


SELECTOR_STYLE: dict[str, str] = {
    "selected": "reverse",
    "meta": "fg:ansibrightblack",
    "preview-title": "bold fg:ansicyan",
    "preview": "fg:ansibrightblack",
    "rule": "fg:ansibrightblack",
    "match": "bold fg:ansiyellow",
    "preview-match": "fg:default",
}


@dataclass(frozen=True)
class SelectionOption:
    value: str
    label: str
    meta: str = ""


def prompt_toolkit_available() -> bool:
    return Application is not None


def require_prompt_toolkit() -> None:
    if not prompt_toolkit_available():
        raise ImportErrorWithExitCode(
            "interactive selectors require prompt_toolkit to be installed",
            exit_code=1,
        )
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ImportErrorWithExitCode(
            "interactive selectors require a real terminal",
            exit_code=1,
        )


def visible_range(selected_index: int, count: int, max_visible: int) -> tuple[int, int]:
    """Return the start and end indexes of the option window that keeps the selection centred."""
    start = max(0, selected_index - (max_visible // 2))
    end = min(count, start + max_visible)
    return max(0, end - max_visible), end


def preview_lines(lines: Sequence[str], height: int) -> list[str]:
    """Return preview lines cut to ``height``, with a final line counting the hidden lines."""
    if len(lines) <= height:
        return list(lines)
    shown = max(0, height - 1)
    return [*lines[:shown], f"... {len(lines) - shown} more"]


def select_one(
    *,
    title: str,
    options: Sequence[SelectionOption],
    default_value: str | None = None,
    max_visible: int = 8,
    preview: Callable[[SelectionOption], Sequence[str]] | None = None,
) -> SelectionOption:
    """Show a fuzzy-filtered menu and return the option the user picks.

    ``preview`` returns the lines to show beside the highlighted option.
    """
    require_prompt_toolkit()
    if not options:
        raise ImportErrorWithExitCode(f"no options available for {title}", exit_code=1)

    selected_index = 0

    if default_value is not None:
        for index, option in enumerate(options):
            if option.value == default_value:
                selected_index = index
                break

    query_buffer = Buffer()
    preview_cache: dict[str, list[str]] = {}

    def contents(option: SelectionOption) -> list[str]:
        if preview is None:
            return []
        if option.value not in preview_cache:
            preview_cache[option.value] = list(preview(option))
        return preview_cache[option.value]

    def current_matches() -> list[OptionMatch]:
        nonlocal selected_index
        matches = match_options(
            options, query_buffer.text, contents if preview is not None else None
        )
        if selected_index >= len(matches):
            selected_index = max(0, len(matches) - 1)
        return matches

    def current_filtered() -> list[SelectionOption]:
        return [match.option for match in current_matches()]

    def render_options() -> list[tuple[str, str]]:
        matches = current_matches()
        start, end = visible_range(selected_index, len(matches), max_visible)

        fragments: list[tuple[str, str]] = []
        visible = matches[start:end]
        for visible_index, match in enumerate(visible, start=start):
            option = match.option
            style = "class:selected" if visible_index == selected_index else ""
            fragments.append((style, "• "))
            fragments.extend(highlight(option.label, match.label_positions, style))
            if option.meta:
                fragments.append((style + " class:meta", f"  {option.meta}"))
            if match.content_hits and not match.label_positions:
                fragments.append((style + " class:meta", f"  {len(match.content_hits)} inside"))
            fragments.append(("", "\n"))
        if not visible:
            fragments.append(("class:meta", "No matches\n"))
        return fragments

    def render_position() -> list[tuple[str, str]]:
        filtered = current_filtered()
        if len(filtered) <= max_visible:
            return []
        return [("class:meta", f"{selected_index + 1}/{len(filtered)}")]

    list_width = (
        max(len(option.label) + (len(option.meta) + 2 if option.meta else 0) for option in options)
        + 12
        if preview is not None
        else None
    )

    def render_preview() -> list[tuple[str, str]]:
        if preview is None:
            return []
        matches = current_matches()
        if not matches:
            return []
        match = matches[selected_index]
        lines = contents(match.option)
        hits = set(match.content_hits)
        ordered = [*match.content_hits, *(line for line in lines if line not in hits)]
        label = match.option.label
        title = f"Inside {label} ({len(lines)})" if lines else f"{label} is empty"
        fragments: list[tuple[str, str]] = [("class:preview-title", f"{title}\n")]
        for line in preview_lines(ordered, max_visible):
            style = "class:preview-match" if line in hits else "class:preview"
            fragments.append((style, f"{line}\n"))
        return fragments

    def render_title() -> list[tuple[str, str]]:
        return [
            ("bold", title),
            ("", "\n"),
            ("class:meta", "Type to filter, arrows to move, Enter to confirm"),
            ("", "\n\n"),
        ]

    def render_search() -> list[tuple[str, str]]:
        return [("bold", "Search: ")]

    kb = KeyBindings()

    @kb.add("up")
    def _move_up(event: Any) -> None:  # pragma: no cover - TTY interaction
        nonlocal selected_index
        filtered = current_filtered()
        if filtered:
            selected_index = max(0, selected_index - 1)
            event.app.invalidate()

    @kb.add("down")
    def _move_down(event: Any) -> None:  # pragma: no cover - TTY interaction
        nonlocal selected_index
        filtered = current_filtered()
        if filtered:
            selected_index = min(len(filtered) - 1, selected_index + 1)
            event.app.invalidate()

    @kb.add("c-c")
    @kb.add("escape")
    def _abort(event: Any) -> None:  # pragma: no cover - TTY interaction
        raise KeyboardInterrupt

    @kb.add("enter", filter=Condition(lambda: True))
    def _accept(event: Any) -> None:  # pragma: no cover - TTY interaction
        filtered = current_filtered()
        if filtered:
            event.app.exit(result=filtered[selected_index])

    def on_text_changed(_buffer: Buffer) -> None:
        nonlocal selected_index
        selected_index = 0

    query_buffer.on_text_changed += on_text_changed

    app: Any = Application(
        layout=Layout(
            HSplit(
                [
                    Window(
                        FormattedTextControl(render_title),
                        height=Dimension(preferred=3),
                    ),
                    Window(
                        BufferControl(buffer=query_buffer, input_processors=[]),
                        height=1,
                        dont_extend_height=True,
                        wrap_lines=False,
                        get_line_prefix=lambda *_: render_search(),  # type: ignore[arg-type]  # list invariance
                    ),
                    Window(height=1, char="-"),
                    VSplit(
                        [
                            Window(
                                FormattedTextControl(render_options),
                                height=Dimension(preferred=max_visible),
                                width=list_width,
                            ),
                            *(
                                [
                                    Window(width=1, char="│", style="class:rule"),
                                    Window(width=1, char=" "),
                                    Window(
                                        FormattedTextControl(render_preview),
                                        height=Dimension(preferred=max_visible + 1),
                                    ),
                                ]
                                if preview is not None
                                else []
                            ),
                        ]
                    ),
                    Window(FormattedTextControl(render_position), height=1),
                ]
            )
        ),
        key_bindings=kb,
        style=Style.from_dict(SELECTOR_STYLE),
        full_screen=False,
        mouse_support=False,
    )
    try:
        result: SelectionOption | None = app.run()
    except EOFError as err:  # pragma: no cover - TTY dependent
        raise ImportErrorWithExitCode("interactive selection cancelled", exit_code=1) from err
    if result is None:
        raise ImportErrorWithExitCode("interactive selection cancelled", exit_code=1)
    return result


@dataclass(frozen=True)
class OptionMatch:
    """An option that matches a search query, and where it matched."""

    option: SelectionOption
    label_positions: tuple[int, ...]
    content_hits: tuple[str, ...]


def fuzzy_positions(query: str, text: str) -> tuple[int, ...] | None:
    """Return the indexes in ``text`` that match ``query`` in order, ignoring case, or None."""
    positions: list[int] = []
    position = -1
    lowered = text.lower()
    for char in query.lower():
        position = lowered.find(char, position + 1)
        if position == -1:
            return None
        positions.append(position)
    return tuple(positions)


def match_options(
    options: Sequence[SelectionOption],
    query: str,
    contents: Callable[[SelectionOption], Sequence[str]] | None = None,
) -> list[OptionMatch]:
    """Return the options that match ``query``, best first.

    A label matches fuzzily. Content lines match as case-insensitive substrings and rank
    after every label match.
    """
    query = query.strip()
    if not query:
        return [OptionMatch(option, (), ()) for option in options]
    ranked: list[tuple[tuple[int, int, str], OptionMatch]] = []
    for option in options:
        positions = fuzzy_positions(query, option.label)
        if positions is None:
            positions = fuzzy_positions(query, f"{option.label} {option.meta}")
            positions = () if positions is not None else None
        hits = tuple(
            line for line in (contents(option) if contents else []) if query.lower() in line.lower()
        )
        if positions is None and not hits:
            continue
        if positions is not None:
            rank = (0, positions[-1] if positions else len(option.label), option.label.lower())
        else:
            rank = (1, -len(hits), option.label.lower())
        ranked.append((rank, OptionMatch(option, positions or (), hits)))
    ranked.sort(key=lambda item: item[0])
    return [match for _rank, match in ranked]


def highlight(text: str, positions: Sequence[int], style: str) -> list[tuple[str, str]]:
    """Return formatted text fragments with the characters at ``positions`` marked as matches."""
    marked = set(positions)
    return [
        (f"{style} class:match" if index in marked else style, char)
        for index, char in enumerate(text)
    ]


def options_from_values(
    values: Iterable[str], *, meta_factory: Callable[[str], str] | None = None
) -> list[SelectionOption]:
    options: list[SelectionOption] = []
    for value in values:
        meta = meta_factory(value) if meta_factory is not None else ""
        options.append(SelectionOption(value=value, label=value, meta=meta))
    return options
