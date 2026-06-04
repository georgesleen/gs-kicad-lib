from __future__ import annotations

import sys
from typing import Any, cast

from .errors import ImportErrorWithExitCode

# prompt_toolkit is optional; pre-annotate as Any to allow the None fallback.
prompt_toolkit_prompt: Any = None
try:
    from prompt_toolkit import prompt as prompt_toolkit_prompt
except ImportError:  # pragma: no cover - runtime dependency only
    pass


def prompt_text(prompt: str) -> str:
    try:
        if (
            prompt_toolkit_prompt is not None
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        ):
            return cast(str, prompt_toolkit_prompt(prompt))
        return input(prompt)
    except EOFError as err:
        raise ImportErrorWithExitCode("interactive input cancelled", exit_code=1) from err


def prompt_yes_no(prompt: str, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = prompt_text(f"{prompt} {suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer yes or no.")
