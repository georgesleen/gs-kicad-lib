"""Tests for LibraryConfig boundary validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from kicad_lib_tools.config import FieldNames, LibraryConfig, _config_from_dict, get_config


def _base(tmp_path: Path, **overrides: str) -> LibraryConfig:
    kwargs: dict[str, object] = {
        "repo_root": tmp_path,
        "library_prefix": "GS",
        "symbol_dir": "symbols",
        "footprint_dir": "footprints",
        "model_dir": "3d-models",
    }
    kwargs.update(overrides)
    return LibraryConfig(**kwargs)  # type: ignore[arg-type]


def test_valid_config_constructs(tmp_path: Path) -> None:
    cfg = _base(tmp_path)
    assert cfg.library_prefix == "GS"


@pytest.mark.parametrize("prefix", ["", "1GS", "GS_X", "G S"])
def test_invalid_library_prefix_raises(tmp_path: Path, prefix: str) -> None:
    with pytest.raises(ValueError, match="library_prefix"):
        _base(tmp_path, library_prefix=prefix)


def test_empty_symbol_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="symbol_dir"):
        _base(tmp_path, symbol_dir="")


def test_empty_footprint_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="footprint_dir"):
        _base(tmp_path, footprint_dir="")


def test_empty_model_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_dir"):
        _base(tmp_path, model_dir="")


def test_env_var_names_follow_library_prefix(tmp_path: Path) -> None:
    cfg = _base(tmp_path, library_prefix="ACME")
    assert cfg.symbol_env_var == "ACME_SYMBOL_DIR"
    assert cfg.footprint_env_var == "ACME_FOOTPRINT_DIR"
    assert cfg.model_env_var == "ACME_3DMODEL_DIR"
    assert cfg.spice_model_env_var == "ACME_SPICE_MODEL_DIR"


def test_loader_rejects_unknown_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"unknown key\(s\) in \[tool.kicad-lib\]: symbols_dir"):
        _config_from_dict(tmp_path, {"library_prefix": "GS", "symbols_dir": "lib"})
    with pytest.raises(ValueError, match="unknown key"):
        _config_from_dict(tmp_path, {"library_prefix": "GS", "fields": {"mfr": "Maker"}})


def test_loader_reads_field_names_over_defaults(tmp_path: Path) -> None:
    cfg = _config_from_dict(tmp_path, {"library_prefix": "GS", "fields": {"lcsc_id": "LCSC"}})
    assert cfg.fields == FieldNames(lcsc_id="LCSC")
    assert cfg.fields.procurement == ("Manufacturer", "MPN", "LCSC", "Package")


def test_loader_keeps_dataclass_defaults(tmp_path: Path) -> None:
    assert _config_from_dict(tmp_path, {"library_prefix": "GS"}) == LibraryConfig(
        repo_root=tmp_path, library_prefix="GS"
    )


def test_loader_rejects_incomplete_passive_types(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="needs library_name_template"):
        _config_from_dict(
            tmp_path,
            {
                "library_prefix": "GS",
                "passive_types": {"Resistors": {"prefix": "R", "value_param": "R"}},
            },
        )


def test_loader_reads_library_descriptions_and_words(tmp_path: Path) -> None:
    cfg = _config_from_dict(
        tmp_path,
        {
            "library_prefix": "GS",
            "library_descriptions": {"Diodes": "diodes"},
            "description_words": {"RF": "radio"},
        },
    )
    assert cfg.library_descriptions == {"Diodes": "diodes"}
    assert cfg.description_words == {"RF": "radio"}
    with pytest.raises(ValueError, match="must be a string"):
        _config_from_dict(tmp_path, {"library_prefix": "GS", "description_words": {"RF": 1}})


def test_loader_reads_family_format_overrides(tmp_path: Path) -> None:
    cfg = _config_from_dict(
        tmp_path,
        {
            "library_prefix": "GS",
            "families": {"crystal": {"name": "Y_{frequency}", "description": ["Crystal"]}},
        },
    )
    assert cfg.family_formats == {"crystal": {"name": "Y_{frequency}", "description": ("Crystal",)}}
    with pytest.raises(ValueError, match="unknown key"):
        _config_from_dict(
            tmp_path, {"library_prefix": "GS", "families": {"crystal": {"title": "x"}}}
        )
    with pytest.raises(ValueError, match="list of strings"):
        _config_from_dict(
            tmp_path, {"library_prefix": "GS", "families": {"crystal": {"description": "Crystal"}}}
        )


def test_loader_requires_library_prefix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="needs library_prefix"):
        _config_from_dict(tmp_path, {})


def test_get_config_requires_a_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="run kicad-lib init"):
        get_config()


def test_get_config_finds_the_config_file_above_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "kicad-lib.toml").write_text('[tool.kicad-lib]\nlibrary_prefix = "ACME"\n')
    (tmp_path / "symbols").mkdir()
    monkeypatch.chdir(tmp_path / "symbols")
    assert get_config().repo_root == tmp_path
    assert get_config().library_prefix == "ACME"
