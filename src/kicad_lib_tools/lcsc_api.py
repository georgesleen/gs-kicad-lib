"""Fetch part metadata from the LCSC product API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .errors import ImportErrorWithExitCode
from .types import LcscId

LCSC_API_URL = "https://wmsc.lcsc.com/ftps/wm/product/detail"


@dataclass
class LCSCPart:
    lcsc_id: LcscId
    manufacturer: str
    mpn: str
    description: str
    datasheet_url: str
    package: str
    category: str
    parent_category: str
    attributes: dict[str, str] = field(default_factory=dict)


def fetch_part(lcsc_id: LcscId) -> LCSCPart:
    """Fetch part details from the LCSC product API."""
    url = f"{LCSC_API_URL}?productCode={lcsc_id}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "gs-kicad-lib/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as err:
        raise ImportErrorWithExitCode(
            f"failed to fetch {lcsc_id} from LCSC: {err}", exit_code=2
        ) from err
    return parse_part(lcsc_id, body)


def parse_part(lcsc_id: LcscId, body: dict[str, Any]) -> LCSCPart:
    """Build an LCSCPart from an LCSC product API response body."""
    if not body.get("ok") or body.get("result") is None:
        msg = body.get("msg", "unknown error")
        raise ImportErrorWithExitCode(f"LCSC API error for {lcsc_id}: {msg}", exit_code=2)

    result = body["result"]

    attributes: dict[str, str] = {}
    for param in result.get("paramVOList") or []:
        name = param.get("paramNameEn", "")
        value = param.get("paramValueEn", "")
        if name and value:
            attributes[name] = value

    def text(key: str) -> str:
        value = result.get(key)
        return value if isinstance(value, str) else ""

    return LCSCPart(
        lcsc_id=lcsc_id,
        manufacturer=text("brandNameEn"),
        mpn=text("productModel"),
        description=text("productDescEn"),
        datasheet_url=text("pdfUrl"),
        package=text("encapStandard"),
        category=text("catalogName"),
        parent_category=text("parentCatalogName"),
        attributes=attributes,
    )
