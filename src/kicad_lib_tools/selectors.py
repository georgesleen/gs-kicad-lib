from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Iterable, Sequence

from .errors import ImportErrorWithExitCode

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import Dimension
except ImportError:  # pragma: no cover - runtime dependency only
    Application = None


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


def select_one(
    *,
    title: str,
    options: Sequence[SelectionOption],
    default_value: str | None = None,
    max_visible: int = 5,
) -> SelectionOption:
    require_prompt_toolkit()
    if not options:
        raise ImportErrorWithExitCode(f"no options available for {title}", exit_code=1)

    filtered_options = list(options)
    selected_index = 0

    if default_value is not None:
        for index, option in enumerate(options):
            if option.value == default_value:
                selected_index = index
                break

    query_buffer = Buffer()

    def current_filtered() -> list[SelectionOption]:
        nonlocal selected_index
        query = query_buffer.text.strip()
        filtered = fuzzy_filter(options, query)
        if not filtered:
            filtered = list(options)
        if selected_index >= len(filtered):
            selected_index = max(0, len(filtered) - 1)
        return filtered

    def render_options():
        filtered = current_filtered()
        start = max(0, selected_index - (max_visible // 2))
        end = min(len(filtered), start + max_visible)
        start = max(0, end - max_visible)

        fragments: list[tuple[str, str]] = []
        visible = filtered[start:end]
        for visible_index, option in enumerate(visible, start=start):
            style = "class:selected" if visible_index == selected_index else ""
            fragments.append((style, "• "))
            fragments.append((style, option.label))
            if option.meta:
                fragments.append((style + " class:meta", f"  {option.meta}"))
            fragments.append(("", "\n"))
        if not visible:
            fragments.append(("class:meta", "No matches\n"))
        return fragments

    def render_title():
        return [("bold", title), ("", "\n"), ("class:meta", "Type to filter, arrows to move, Enter to confirm"), ("", "\n\n")]

    def render_search():
        return [("bold", "Search: ")]

    kb = KeyBindings()

    @kb.add("up")
    def _move_up(event) -> None:  # pragma: no cover - TTY interaction
        nonlocal selected_index
        filtered = current_filtered()
        if filtered:
            selected_index = max(0, selected_index - 1)
            event.app.invalidate()

    @kb.add("down")
    def _move_down(event) -> None:  # pragma: no cover - TTY interaction
        nonlocal selected_index
        filtered = current_filtered()
        if filtered:
            selected_index = min(len(filtered) - 1, selected_index + 1)
            event.app.invalidate()

    @kb.add("c-c")
    @kb.add("escape")
    def _abort(event) -> None:  # pragma: no cover - TTY interaction
        raise KeyboardInterrupt

    @kb.add("enter", filter=Condition(lambda: True))
    def _accept(event) -> None:  # pragma: no cover - TTY interaction
        filtered = current_filtered()
        if filtered:
            event.app.exit(result=filtered[selected_index])

    def on_text_changed(_buffer: Buffer) -> None:
        nonlocal selected_index
        selected_index = 0

    query_buffer.on_text_changed += on_text_changed

    app = Application(
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
                        get_line_prefix=lambda *_: render_search(),
                    ),
                    Window(height=1, char="-"),
                    Window(
                        FormattedTextControl(render_options),
                        height=Dimension(preferred=max_visible),
                    ),
                ]
            )
        ),
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )
    try:
        result = app.run()
    except EOFError as err:  # pragma: no cover - TTY dependent
        raise ImportErrorWithExitCode(
            "interactive selection cancelled", exit_code=1
        ) from err
    if result is None:
        raise ImportErrorWithExitCode("interactive selection cancelled", exit_code=1)
    return result


def fuzzy_filter(
    options: Sequence[SelectionOption], query: str
) -> list[SelectionOption]:
    if not query:
        return list(options)

    scored: list[tuple[int, SelectionOption]] = []
    for option in options:
        haystack = f"{option.label} {option.meta}".lower()
        score = fuzzy_score(query.lower(), haystack)
        if score is not None:
            scored.append((score, option))
    scored.sort(key=lambda item: (item[0], item[1].label.lower()))
    return [option for _score, option in scored]


def fuzzy_score(query: str, text: str) -> int | None:
    position = -1
    score = 0
    for char in query:
        next_position = text.find(char, position + 1)
        if next_position == -1:
            return None
        gap = next_position - position
        score += gap
        position = next_position
    return score


def options_from_values(
    values: Iterable[str], *, meta_factory: callable | None = None
) -> list[SelectionOption]:
    options: list[SelectionOption] = []
    for value in values:
        meta = meta_factory(value) if meta_factory is not None else ""
        options.append(SelectionOption(value=value, label=value, meta=meta))
    return options
