from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from .errors import ImportErrorWithExitCode
from .paths import DEFAULT_CONVERTER, REPO_ROOT


def resolve_converter_command(provided: str | None) -> str:
    if provided:
        return provided
    env_value = os.environ.get("GS_EASYEDA2KICAD_CMD")
    if env_value:
        return env_value
    if DEFAULT_CONVERTER.is_file():
        return f"{DEFAULT_CONVERTER} -m easyeda2kicad"
    return "easyeda2kicad"


def run_converter(
    converter_command: str, lcsc_id: str, output_base: Path, verbose: bool
) -> subprocess.CompletedProcess[str]:
    command = shlex.split(converter_command) + [
        "--full",
        f"--lcsc_id={lcsc_id}",
        f"--output={output_base}",
    ]
    if verbose:
        print("Running converter:")
        print("  " + " ".join(shlex.quote(part) for part in command))
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as err:
        raise ImportErrorWithExitCode(
            f"converter command not found: {converter_command}", exit_code=1
        ) from err

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ImportErrorWithExitCode(
            f"converter failed with exit code {result.returncode}: {details}",
            exit_code=2,
        )
    return result

