"""Regression tests that CLI entry points and script shims resolve.

These guard against two breakages seen during the easyeda2kicad migration:
- a ``[project.scripts]`` target pointing at a non-existent symbol
  (``kicad_lib_tools.__main__:main`` before it was added);
- a ``scripts/*.py`` shim importing a deleted package (``easyeda_import``).
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from kicad_lib_tools import __main__ as import_main
from kicad_lib_tools.errors import ImportErrorWithExitCode

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


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


@pytest.mark.parametrize("shim", sorted(SCRIPTS_DIR.glob("*.py")))
def test_script_shim_imports(shim: Path) -> None:
    """Each scripts/*.py shim must load without raising ImportError.

    Loading runs only top-level imports; the ``if __name__ == '__main__'``
    guard keeps the wrapped entry point from executing.
    """
    spec = importlib.util.spec_from_file_location(f"_shim_{shim.stem}", shim)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass/typing machinery can resolve the module.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)


def test_main_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_main, "run_import", lambda args: None)
    assert import_main.main([]) == 0


def test_main_returns_error_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(args: argparse.Namespace) -> None:
        raise ImportErrorWithExitCode("nope", exit_code=2)

    monkeypatch.setattr(import_main, "run_import", boom)
    assert import_main.main([]) == 2


def test_main_returns_130_on_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(args: argparse.Namespace) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(import_main, "run_import", interrupt)
    assert import_main.main([]) == 130
