"""Tests for the ``kicad-lib`` entry point and its command dispatch."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import tomllib
from pathlib import Path

import pytest

from kicad_lib_tools import __main__ as cli_main
from kicad_lib_tools.config import ConfigError
from kicad_lib_tools.errors import ImportErrorWithExitCode

REPO_ROOT = Path(__file__).resolve().parent.parent


def _console_scripts() -> dict[str, str]:
    """Return the ``[project.scripts]`` mapping from pyproject.toml."""
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"]["scripts"]


@pytest.mark.parametrize("target", _console_scripts().values())
def test_console_script_target_resolves(target: str) -> None:
    """Each 'module:attr' console-script target must import and expose attr."""
    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    assert callable(getattr(module, attr))


def test_import_command_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_main, "run_import", lambda args: None)
    assert cli_main.import_command([]) == 0


def test_import_command_returns_error_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(args: argparse.Namespace) -> None:
        raise ImportErrorWithExitCode("nope", exit_code=2)

    monkeypatch.setattr(cli_main, "run_import", boom)
    assert cli_main.import_command([]) == 2


def test_import_command_returns_130_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(args: argparse.Namespace) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_main, "run_import", interrupt)
    assert cli_main.import_command([]) == 130


def test_main_dispatches_to_the_named_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def record(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setitem(cli_main.COMMANDS, "validate", (record, ""))
    assert cli_main.main(["validate", "symbols"]) == 0
    assert calls == [["symbols"]]


def test_main_rejects_unknown_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["frobnicate"]) == 2
    assert "unknown command 'frobnicate'" in capsys.readouterr().err


def test_main_help_lists_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert all(name in out for name in cli_main.COMMANDS)


def test_main_reports_config_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(argv: list[str]) -> int:
        raise ConfigError("kicad-lib.toml: unknown key(s) in [tool.kicad-lib]: x")

    monkeypatch.setitem(cli_main.COMMANDS, "validate", (broken, ""))
    assert cli_main.main(["validate"]) == 2
    assert "Error: kicad-lib.toml: unknown key" in capsys.readouterr().err
