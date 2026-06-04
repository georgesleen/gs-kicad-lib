from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .errors import ImportErrorWithExitCode
from .paths import REPO_ROOT
from .types import ConverterCommand, LcscId


def resolve_converter_command(provided: str | None) -> ConverterCommand:
    return ConverterCommand(provided) if provided else ConverterCommand("easyeda2kicad")


def run_converter(
    converter_command: ConverterCommand,
    lcsc_id: LcscId,
    output_base: Path,
    verbose: bool,
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
