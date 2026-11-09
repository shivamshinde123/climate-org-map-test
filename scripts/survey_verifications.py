"""Mark organizations Verified when they answered the GCC survey themselves.

Survey evidence lives in ``Data/Survey/survey-verifications.json`` (matched on
EIN, which survives IRS rebuilds). It is applied after enrichment on every
pipeline run, because Jev never sees survey evidence and would otherwise reset
these records to "Not Verified".
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "Data" / "Survey" / "survey-verifications.json"


def apply_survey_verifications(features: list[dict], overrides_path: Path = DEFAULT_PATH) -> int:
    """Set verification fields on matching features; return how many were marked."""
    if not overrides_path.exists():
        return 0
    by_ein = {str(o["ein"]): o for o in json.loads(overrides_path.read_text(encoding="utf-8"))}
    marked = 0
    for feature in features:
        properties = feature.get("properties", {})
        override = by_ein.get(str(properties.get("source_id", "")))
        if not override:
            continue
        properties["status"] = "Verified"
        properties["gcc_verification"] = "Verified"
        properties["validated"] = True
        properties["verification_source"] = f"GCC survey ({override['survey']}): {override['evidence']}"
        marked += 1
    return marked
