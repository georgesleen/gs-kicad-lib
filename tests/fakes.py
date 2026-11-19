"""Test doubles for the kicad_lib_tools seams."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from kicad_lib_tools.selectors import SelectionOption


@dataclass
class Question:
    """One question a ScriptedPrompter received: its kind, text, and default."""

    kind: str
    prompt: str
    default: object


@dataclass
class ScriptedPrompter:
    """Prompter that answers from a script and records every question.

    Each answer is a string. A select answer is an option value, and ``None`` takes the
    default. A text or yes/no answer of ``""`` also takes the default.
    """

    answers: list[str | None]
    questions: list[Question] = field(default_factory=list)

    def _next(self, question: Question) -> str | None:
        self.questions.append(question)
        if not self.answers:
            raise AssertionError(f"unscripted question: {question}")
        return self.answers.pop(0)

    def text(self, prompt: str) -> str:
        return self._next(Question("text", prompt, None)) or ""

    def yes_no(self, prompt: str, default: bool) -> bool:
        answer = self._next(Question("yes_no", prompt, default))
        return default if not answer else answer.lower().startswith("y")

    def select(
        self,
        *,
        title: str,
        options: Sequence[SelectionOption],
        default_value: str | None = None,
        preview: Callable[[SelectionOption], Sequence[str]] | None = None,
    ) -> SelectionOption:
        answer = self._next(Question("select", title, default_value))
        value = default_value if answer is None else answer
        for option in options:
            if option.value == value:
                return option
        raise AssertionError(f"{value!r} is not an option of {title!r}")
