from __future__ import annotations

import pytest

from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.interaction import prompt_text, prompt_yes_no


def test_prompt_text_uses_prompt_toolkit_in_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kicad_lib_tools.interaction.prompt_toolkit_prompt", lambda prompt: "typed")
    monkeypatch.setattr("kicad_lib_tools.interaction.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("kicad_lib_tools.interaction.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "fallback")

    assert prompt_text("Prompt: ") == "typed"


def test_prompt_text_falls_back_to_input_without_prompt_toolkit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("kicad_lib_tools.interaction.prompt_toolkit_prompt", None)
    monkeypatch.setattr("builtins.input", lambda prompt: "fallback")

    assert prompt_text("Prompt: ") == "fallback"


def test_prompt_text_wraps_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_eof(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("kicad_lib_tools.interaction.prompt_toolkit_prompt", None)
    monkeypatch.setattr("builtins.input", raise_eof)

    with pytest.raises(ImportErrorWithExitCode, match="interactive input cancelled"):
        prompt_text("Prompt: ")


def test_prompt_yes_no_accepts_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kicad_lib_tools.interaction.prompt_text", lambda prompt: "")
    assert prompt_yes_no("Proceed?", default=True) is True
