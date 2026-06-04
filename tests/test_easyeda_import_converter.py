from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kicad_lib_tools.converter import resolve_converter_command, run_converter
from kicad_lib_tools.errors import ImportErrorWithExitCode
from kicad_lib_tools.paths import REPO_ROOT
from kicad_lib_tools.types import ConverterCommand, LcscId


def test_resolve_converter_command_prefers_explicit_command() -> None:
    assert resolve_converter_command("custom-easyeda2kicad") == ConverterCommand("custom-easyeda2kicad")


def test_resolve_converter_command_defaults_to_easyeda2kicad() -> None:
    assert resolve_converter_command(None) == ConverterCommand("easyeda2kicad")


def test_run_converter_invokes_upstream_compatible_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("kicad_lib_tools.converter.subprocess.run", fake_run)

    output_base = Path("/tmp/stage/generated")
    result = run_converter(
        converter_command=ConverterCommand("easyeda2kicad"),
        lcsc_id=LcscId("C2040"),
        output_base=output_base,
        verbose=False,
    )

    assert result.returncode == 0
    assert calls == [
        (
            (
                [
                    "easyeda2kicad",
                    "--full",
                    "--lcsc_id=C2040",
                    f"--output={output_base}",
                ],
            ),
            {
                "cwd": REPO_ROOT,
                "capture_output": True,
                "text": True,
                "check": False,
            },
        )
    ]


def test_run_converter_wraps_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("missing")

    monkeypatch.setattr("kicad_lib_tools.converter.subprocess.run", fake_run)

    with pytest.raises(ImportErrorWithExitCode, match="converter command not found"):
        run_converter(
            converter_command=ConverterCommand("missing-binary"),
            lcsc_id=LcscId("C2040"),
            output_base=Path("/tmp/stage/generated"),
            verbose=False,
        )


def test_run_converter_reports_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=7,
            stdout="",
            stderr="converter exploded",
        )

    monkeypatch.setattr("kicad_lib_tools.converter.subprocess.run", fake_run)

    with pytest.raises(
        ImportErrorWithExitCode,
        match=r"converter failed with exit code 7: converter exploded",
    ):
        run_converter(
            converter_command=ConverterCommand("easyeda2kicad"),
            lcsc_id=LcscId("C2040"),
            output_base=Path("/tmp/stage/generated"),
            verbose=False,
        )
