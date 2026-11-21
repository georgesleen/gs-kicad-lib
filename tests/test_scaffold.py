from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from kicad_lib_tools.config import _config_from_dict, get_config
from kicad_lib_tools.scaffold import config_text, create_library, main


def test_create_library_makes_a_loadable_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "acme-lib"

    create_library(root, "ACME")

    for name in ("symbols", "footprints", "3d-models", "spice-models"):
        assert (root / name).is_dir()
    assert (root / ".gitignore").read_text() == "tmp/\nfp-info-cache\n"
    monkeypatch.chdir(root)
    assert get_config().library_prefix == "ACME"
    assert get_config().repo_root == root


def test_create_library_appends_only_missing_gitignore_lines(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("tmp/\n")
    create_library(tmp_path, "ACME")
    assert (tmp_path / ".gitignore").read_text() == "tmp/\nfp-info-cache\n"


def test_create_library_refuses_an_existing_library(tmp_path: Path) -> None:
    create_library(tmp_path, "ACME")
    with pytest.raises(FileExistsError):
        create_library(tmp_path, "ACME")


def test_main_rejects_an_invalid_prefix(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path), "--prefix", "AC_ME"]) == 1
    assert "must be a letter" in capsys.readouterr().err
    assert not (tmp_path / "kicad-lib.toml").exists()


def test_config_text_round_trips() -> None:
    raw = tomllib.loads(config_text("ACME"))["tool"]["kicad-lib"]
    assert _config_from_dict(Path("/lib"), raw).library_prefix == "ACME"
