"""Domain types — opaque wrappers that make invalid states unrepresentable."""

from __future__ import annotations

import re
from typing import NewType

LcscId = NewType("LcscId", str)
ConverterCommand = NewType("ConverterCommand", str)
LibraryName = NewType("LibraryName", str)

_LCSC_RE = re.compile(r"^C\d+$", re.IGNORECASE)


def lcsc_id(raw: str) -> LcscId:
    """Validate and normalise a raw LCSC ID string to ``LcscId``."""
    if not _LCSC_RE.match(raw):
        raise ValueError(f"Invalid LCSC ID: {raw!r} (expected C followed by digits)")
    return LcscId(raw.upper())
