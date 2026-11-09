"""Add GCC-survey organizations that are not in the IRS data to the map.

Rows come from ``Data/Survey/survey-organizations.csv``: organizations that
answered the survey themselves (so they are shown as verified) but have no IRS
record, such as town committees. Rows with a survey street address are pinned
there (coordinates stored in the CSV); the rest fall back to the ZIP or town
center. The step is idempotent: earlier survey records are replaced.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

try:
    from .geocode_organizations import FALLBACK_SPREAD, _scatter_around, load_city_centroids, load_zip_centroids, match_city
except ImportError:  # Allows direct execution from the scripts directory.
    from geocode_organizations import FALLBACK_SPREAD, _scatter_around, load_city_centroids, load_zip_centroids, match_city  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = PROJECT_ROOT / "Data" / "Survey" / "survey-organizations.csv"
CITY_CENTROIDS = PROJECT_ROOT / "Data" / "Geocoding" / "city_centroids.csv"
ZIP_CENTROIDS = PROJECT_ROOT / "Data" / "Geocoding" / "zip_centroids.csv"
SOURCE = "GCC survey"

# Survey column -> (schema field, frontend gcc_* field).
_CATEGORY_FIELDS = {
    "organization_type": "gcc_organization_type",
    "audience_focus": "gcc_audience_focus",
    "adaptation_vs_mitigation": "gcc_resilience",
    "advocacy_vs_action": "gcc_activity",
    "climate_categories": "gcc_climate_category",
    "reach": "gcc_reach",
}


def survey_feature(row: dict, city_centroids: dict, zip_centroids: dict | None = None) -> dict:
    """Build one map feature with the full schema from a cleaned survey row."""
    org_id = "survey_" + hashlib.sha256(f"{row['name']}|{row['state']}".lower().encode()).hexdigest()[:16]
    properties = {
        "id": org_id, "name": row["name"], "website_url": row["website_url"], "source_url": "",
        "email": "", "phone": "", "address": row.get("address") or "", "city": row["city"], "state": row["state"],
        "postal_code": row.get("postal_code") or "", "summary": "", "source": SOURCE, "source_id": row["row_uuid"],
        "ntee_code": "", "ntee_label": "", "irs_category": "",
        "status": "Verified", "gcc_verification": "Verified", "validated": True,
        "action_category": "Unknown", "gcc_action_category": "Unknown",
        "verification_source": f"GCC survey ({row['survey']}): answered the survey itself (row {row['row_uuid']}).",
        "notes": "Added from the GCC survey.",
    }
    for field, gcc_field in _CATEGORY_FIELDS.items():
        properties[field] = properties[gcc_field] = row.get(field) or "Unknown"

    # Survey street address, geocoded once with the Census one-line geocoder and stored in the CSV.
    if row.get("latitude") and row.get("longitude"):
        latitude, longitude = float(row["latitude"]), float(row["longitude"])
        properties.update(latitude=latitude, longitude=longitude, location_precision="census_address_range")
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [longitude, latitude]}, "properties": properties}

    zip_centroids = zip_centroids or {}
    # Many New England towns are missing from the Census place list, so a town's
    # main ZIP (placement only, never displayed) is tried first when given.
    center = (
        zip_centroids.get(row.get("placement_zip") or "")
        or city_centroids.get((row["city"].upper(), row["state"].upper()))
        or match_city(row["city"].upper(), row["state"].upper(), city_centroids)
    )
    geometry = None
    properties["location_precision"] = "unavailable"
    if center:
        # Same seed the geocoder's fallback uses (source_id), so a later geocoding pass
        # lands on the identical point.
        longitude, latitude = _scatter_around(center[0], center[1], row["row_uuid"], FALLBACK_SPREAD)
        geometry = {"type": "Point", "coordinates": [longitude, latitude]}
        precision = "zip_level_fallback" if zip_centroids.get(row.get("placement_zip") or "") else "city_level_fallback"
        properties.update(latitude=latitude, longitude=longitude, location_precision=precision)
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def add_survey_organizations(
    payload: dict, path: Path = DEFAULT_PATH, centroids_path: Path = CITY_CENTROIDS, zips_path: Path = ZIP_CENTROIDS
) -> int:
    """Replace any earlier survey records with fresh ones; return how many were added."""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    city_centroids = load_city_centroids(centroids_path)
    zip_centroids = load_zip_centroids(zips_path) if zips_path.exists() else {}
    features = [f for f in payload.get("features", []) if f.get("properties", {}).get("source") != SOURCE]
    features.extend(survey_feature(row, city_centroids, zip_centroids) for row in rows)
    payload["features"] = features
    return len(rows)
