"""Shared helpers for the ProPublica Nonprofit Explorer integration.

The project already identifies IRS EO BMF organizations by EIN.  ProPublica's
organization endpoint uses that same identifier, so EIN is the stable join key
throughout this integration.  This module deliberately uses only Python's
standard library so the data fetch does not add another project dependency.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROPUBLICA_API_BASE = "https://projects.propublica.org/nonprofits/api/v2"
DEFAULT_DATA_DIR = Path("Data/ProPublica")


def normalize_ein(value: Any) -> str:
    """Return an EIN as exactly nine digits, or an empty string when invalid.

    Spreadsheet and JSON readers sometimes turn an EIN into a number, append a
    decimal suffix, or preserve its conventional hyphen.  Removing non-digits
    and padding on the left makes those representations comparable while still
    rejecting values that cannot be an EIN.
    """

    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if not digits or len(digits) > 9:
        return ""
    return digits.zfill(9)


def organization_features() -> list[dict[str, Any]]:
    """Every approved map organization, read from Supabase (keys from ``.env``)."""

    try:
        from . import supabase_store as store
        from .load_environment import load_environment
    except ImportError:  # Direct execution puts ``scripts`` on sys.path.
        import supabase_store as store  # type: ignore
        from load_environment import load_environment  # type: ignore
    load_environment(Path(__file__).resolve().parents[1] / ".env")
    return store.load_payload()["features"]


def feature_ein(feature: dict[str, Any]) -> str:
    """Find the EIN in the known map fields without assuming one exact export."""

    properties = feature.get("properties") or {}
    for field in ("ein", "EIN", "source_id", "organization_id"):
        ein = normalize_ein(properties.get(field))
        if ein:
            return ein
    return ""


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty value among alternate API/local field names."""

    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None
