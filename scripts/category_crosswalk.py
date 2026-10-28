"""Resolve source classification values into the GCC controlled taxonomy.

The JSON crosswalk is the single authority for category-level mappings shared
by IRS EO BMF, ProPublica, and generic external-source adapters.  This module
only maps fields supported by the source category itself; evidence-dependent
fields such as audience and reach remain outside this resolver.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_CROSSWALK_PATH = (
    Path(__file__).resolve().parents[1]
    / "Data"
    / "ProPublica"
    / "category-crosswalk.json"
)
TARGET_CATEGORY_FIELDS = (
    "climate_category",
    "action_category",
    "activity",
    "resilience",
)


def normalized_category_key(value: object) -> str:
    """Return a punctuation- and case-insensitive source-category key."""

    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


@lru_cache(maxsize=None)
def _load_payload(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    return json.loads(path.read_text(encoding="utf-8"))


def load_crosswalk(path: Path | None = None) -> dict[str, Any]:
    """Load the versioned machine-readable source-to-target crosswalk."""

    resolved = (path or DEFAULT_CROSSWALK_PATH).resolve()
    return _load_payload(str(resolved))


def _label_index(mappings: dict[str, dict[str, str]]) -> dict[str, str]:
    """Index exact NTEE labels so equivalent external labels resolve safely."""

    result: dict[str, str] = {}
    for code, mapping in mappings.items():
        label = normalized_category_key(mapping.get("ntee_label", ""))
        if label:
            result[label] = code
    return result


def resolve_source_category(
    ntee_code: object = "",
    source_category: object = "",
    *,
    crosswalk_path: Path | None = None,
) -> dict[str, str]:
    """Resolve an NTEE code or equivalent label to supported GCC categories.

    An explicit valid NTEE code wins.  Otherwise a code embedded in the source
    label or an exact normalized NTEE label may resolve the mapping.  Unknown
    labels never leak into target fields.
    """

    payload = load_crosswalk(crosswalk_path)
    mappings: dict[str, dict[str, str]] = payload.get("ntee_mappings") or {}
    code = str(ntee_code or "").strip().upper()
    source_text = str(source_category or "").strip()
    basis = "unmapped source category"

    if code not in mappings:
        embedded = re.search(r"\b([A-Z]\d{2})\b", source_text.upper())
        code = embedded.group(1) if embedded and embedded.group(1) in mappings else ""
        if code:
            basis = f"source category code -> NTEE {code}"

    if not code and source_text:
        code = _label_index(mappings).get(normalized_category_key(source_text), "")
        if code:
            basis = f"source category label -> NTEE {code}"

    mapping = mappings.get(code, {})
    if code and basis == "unmapped source category":
        basis = f"IRS/ProPublica NTEE {code}"

    result = {
        field: str(mapping.get(field) or "Unknown")
        for field in TARGET_CATEGORY_FIELDS
    }
    result.update(
        {
            "ntee_code": code,
            "ntee_label": str(mapping.get("ntee_label") or ""),
            "mapping_basis": basis,
            "mapping_version": str(payload.get("version") or "unversioned"),
        }
    )
    return result
