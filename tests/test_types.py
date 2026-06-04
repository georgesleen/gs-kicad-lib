import pytest

from kicad_lib_tools.types import lcsc_id, LcscId


def test_lcsc_id_valid_uppercase() -> None:
    assert lcsc_id("C2040") == LcscId("C2040")


def test_lcsc_id_normalises_lowercase() -> None:
    assert lcsc_id("c2040") == LcscId("C2040")


def test_lcsc_id_rejects_no_prefix() -> None:
    with pytest.raises(ValueError, match="Invalid LCSC ID"):
        lcsc_id("2040")


def test_lcsc_id_rejects_wrong_prefix() -> None:
    with pytest.raises(ValueError, match="Invalid LCSC ID"):
        lcsc_id("R100")


def test_lcsc_id_rejects_empty() -> None:
    with pytest.raises(ValueError, match="Invalid LCSC ID"):
        lcsc_id("")


def test_lcsc_id_rejects_letters_after_prefix() -> None:
    with pytest.raises(ValueError, match="Invalid LCSC ID"):
        lcsc_id("CABC")
