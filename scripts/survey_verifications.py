"""Mark organizations Verified when they answered the GCC survey themselves.

Survey evidence lives in ``Data/Survey/survey-verifications.json`` (matched on
EIN, which survives IRS rebuilds), together with the organization's own survey
answers for the category filters. It is applied before enrichment (so the paid
run knows to skip Jev for these records) and again after it, so no stage can
overwrite the survey data.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "Data" / "Survey" / "survey-verifications.json"
# Survey column -> frontend gcc_* field (same mapping as survey-only organizations).
_CATEGORY_FIELDS = {
    "organization_type": "gcc_organization_type",
    "audience_focus": "gcc_audience_focus",
    "adaptation_vs_mitigation": "gcc_resilience",
    "advocacy_vs_action": "gcc_activity",
    "climate_categories": "gcc_climate_category",
    "reach": "gcc_reach",
}


def is_survey_verified(properties: dict) -> bool:
    """True when the organization answered the GCC survey itself (its answers beat Jev)."""
    return str(properties.get("verification_source", "")).startswith("GCC survey")


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
        # The organization's own answers replace IRS/Jev categories; unanswered
        # questions keep their current value.
        for field, value in override.get("survey_categories", {}).items():
            properties[field] = properties[_CATEGORY_FIELDS[field]] = value
        marked += 1
    return marked
