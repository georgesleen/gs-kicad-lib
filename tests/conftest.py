from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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


@pytest.fixture
def repo(tmp_path: Path):
    """Point the kicad_lib_tools config at an empty repo under ``tmp_path``."""
    from kicad_lib_tools.config import LibraryConfig, set_config

    config = LibraryConfig(repo_root=tmp_path)
    config.symbol_path.mkdir()
    config.footprint_path.mkdir()
    set_config(config)
    return config


@pytest.fixture(autouse=True)
def reset_kicad_lib_config():
    """Reset the kicad_lib_tools config cache between tests."""
    from kicad_lib_tools.config import reset_config

    reset_config()
    yield
    reset_config()
