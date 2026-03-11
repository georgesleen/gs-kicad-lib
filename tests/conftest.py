from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--create-reference",
        action="store_true",
        default=False,
        help="Create or update reference files for regression tests",
    )


@pytest.fixture
def create_reference(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--create-reference"))


@pytest.fixture
def reference_dir() -> Path:
    return Path(__file__).parent / "reference_outputs"


@pytest.fixture(scope="session")
def check_symbol_fields_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "check-symbol-fields.py"
    spec = importlib.util.spec_from_file_location("check_symbol_fields", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"failed to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
