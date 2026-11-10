#!/usr/bin/env python3
"""Normalize arbitrary organization records into the GCC schema deterministically.

This source adapter accepts CSV, JSON arrays, record envelopes, or GeoJSON. It
maps common column aliases, canonicalizes recognized category values, and fills
missing categories using the same ordered IRS/NTEE and keyword rules as the map
builder. The output vocabulary is closed: uncontrolled source labels can be
retained as provenance, but they can never leak into filter-facing fields.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

try:
    from .category_crosswalk import resolve_source_category
    from .build_irs_dataset import (
        clean_text,
        gcc_classification,
        infer_audience,
        infer_organization_type,
        infer_reach,
    )
except ImportError:  # Allows direct execution from the repository root.
    from category_crosswalk import resolve_source_category  # type: ignore
    from build_irs_dataset import (  # type: ignore
        clean_text,
        gcc_classification,
        infer_audience,
        infer_organization_type,
        infer_reach,
    )


MAPPING_VERSION = "gcc-schema-v1"

# Required normalized fields shared by all future organization sources.
SCHEMA_FIELDS = [
    "name", "website_url", "source_url", "email", "phone", "address", "city",
    "state", "postal_code", "latitude", "longitude", "action_category",
    "climate_categories", "organization_type", "reach", "status", "summary",
    "tags", "social_links", "validated", "notes", "advocacy_vs_action",
    "audience_focus", "adaptation_vs_mitigation",
]

# Common spelling and vendor variations recognized without a custom field map.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "organization_name", "organisation_name", "org_name", "title"),
    "website_url": ("website_url", "website", "url", "homepage"),
    "source_url": ("source_url", "record_url", "profile_url"),
    "email": ("email", "email_address", "contact_email"),
    "phone": ("phone", "phone_number", "telephone", "contact_phone"),
    "address": ("address", "street", "street_address", "address_1"),
    "city": ("city", "town", "locality"),
    "state": ("state", "state_code", "region", "province"),
    "postal_code": ("postal_code", "zip", "zipcode", "zip_code"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "lng", "long", "x"),
    "summary": ("summary", "description", "mission", "about"),
    "tags": ("tags", "topics", "keywords"),
    "social_links": ("social_links", "social", "social_media"),
    "notes": ("notes", "note", "comments"),
}

CATEGORY_INPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "organization_type": ("organization_type", "organisation_type", "org_type", "entity_type", "type"),
    "audience_focus": ("audience_focus", "audience", "target_audience"),
    "adaptation_vs_mitigation": ("adaptation_vs_mitigation", "resilience", "climate_response"),
    "advocacy_vs_action": ("advocacy_vs_action", "activity", "activity_type"),
    "action_category": ("action_category", "action", "program_type"),
    "climate_categories": ("climate_categories", "climate_category", "focus_area", "climate_focus"),
    "reach": ("reach", "scope", "geographic_reach", "service_area"),
    "status": ("status", "verification", "verification_status", "verified"),
}

# This is the canonical controlled vocabulary used by the normalizer, Jev, and
# frontend filters. Add or rename a category here only with a schema migration.
CATEGORY_OPTIONS: dict[str, tuple[str, ...]] = {
    "organization_type": (
        "Nonprofit / Grassroots", "Coalition", "Municipality", "Business", "Academic",
        "Tribal/Indigenous", "Committee", "Unknown",
    ),
    # Combined audiences are single values, in the GCC schema's fixed order.
    "audience_focus": (
        "Residents", "Municipality", "Businesses", "Residents / Municipality",
        "Residents / Businesses", "Residents / Municipality / Businesses",
        "Municipality / Businesses", "Unknown",
    ),
    "adaptation_vs_mitigation": ("Adaptation", "Both", "Mitigation", "Unknown"),
    "advocacy_vs_action": ("Action", "Advocacy", "Both", "Unknown"),
    "action_category": (
        "Community Engagement", "Conservation", "Advocacy/Policy", "Other", "Unknown",
    ),
    "climate_categories": (
        "Environmental", "Waste Reduction", "Green Economics", "Food & Food Waste",
        "Transportation", "Energy Efficiency", "Unknown",
    ),
    "reach": ("Town / City", "Regional", "State / National", "Unknown"),
    "status": ("Not Verified", "Verified"),
}

# Synonyms are normalized before lookup, so punctuation, spaces, and case do not
# need separate entries. Each mapping must resolve to a CATEGORY_OPTIONS value.
CATEGORY_SYNONYMS: dict[str, dict[str, str]] = {
    "organization_type": {
        "academicinstitution": "Academic", "university": "Academic", "college": "Academic",
        "company": "Business", "privatebusiness": "Business", "forprofit": "Business",
        "alliance": "Coalition", "network": "Coalition", "collaborative": "Coalition",
        "government": "Municipality", "publicagency": "Municipality",
        "municipalgovernmentaffiliated": "Municipality",
        "tribal": "Tribal/Indigenous", "indigenous": "Tribal/Indigenous", "tribe": "Tribal/Indigenous",
        "citygovernment": "Municipality", "towngovernment": "Municipality",
        "nonprofit": "Nonprofit / Grassroots", "ngo": "Nonprofit / Grassroots",
        "charity": "Nonprofit / Grassroots", "grassroots": "Nonprofit / Grassroots",
    },
    "audience_focus": {
        "business": "Businesses", "companies": "Businesses", "employers": "Businesses",
        "government": "Municipality", "municipalities": "Municipality", "cities": "Municipality",
        "community": "Residents", "public": "Residents", "individuals": "Residents",
    },
    "adaptation_vs_mitigation": {
        "adaptivecapacity": "Adaptation", "climateresilience": "Adaptation",
        "emissionsreduction": "Mitigation", "decarbonization": "Mitigation",
        "adaptationandmitigation": "Both", "mitigationandadaptation": "Both",
    },
    "advocacy_vs_action": {
        "implementation": "Action", "directservice": "Action", "programdelivery": "Action",
        "policy": "Advocacy", "lobbying": "Advocacy", "campaigning": "Advocacy",
        "advocacyandaction": "Both", "actionandadvocacy": "Both",
    },
    "action_category": {
        "education": "Community Engagement", "outreach": "Community Engagement",
        "organizing": "Community Engagement", "naturalresourceprotection": "Conservation",
        "policy": "Advocacy/Policy", "advocacy": "Advocacy/Policy",
    },
    "climate_categories": {
        "nature": "Environmental", "conservation": "Environmental",
        "landconservation": "Environmental", "waterconservation": "Environmental",
        "energy": "Energy Efficiency", "cleanenergy": "Energy Efficiency", "renewableenergy": "Energy Efficiency",
        "environment": "Environmental", "climate": "Environmental", "sustainability": "Environmental",
        "food": "Food & Food Waste", "composting": "Food & Food Waste", "agriculture": "Food & Food Waste",
        "greeneconomy": "Green Economics", "sustainablebusiness": "Green Economics",
        "transit": "Transportation", "mobility": "Transportation", "electricvehicles": "Transportation",
        "recycling": "Waste Reduction", "zerowaste": "Waste Reduction", "reuse": "Waste Reduction",
    },
    "reach": {
        "international": "State / National", "worldwide": "State / National",
        "global": "State / National", "municipality": "Town / City", "city": "Town / City",
        "local": "Town / City", "county": "Regional", "multicounty": "Regional",
        "statewide": "State / National", "national": "State / National",
    },
    "status": {
        "true": "Verified", "yes": "Verified", "validated": "Verified", "approved": "Verified",
        "false": "Not Verified", "no": "Not Verified", "unverified": "Not Verified",
        "notvalidated": "Not Verified", "pending": "Not Verified",
    },
}


def normalized_key(value: object) -> str:
    """Create a case- and punctuation-insensitive comparison key."""
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def index_record(record: dict) -> dict[str, object]:
    """Index source columns by normalized names for alias-based lookup."""
    return {normalized_key(key): value for key, value in record.items()}


def first_value(indexed: dict[str, object], aliases: Iterable[str]) -> object:
    """Return the first nonblank source value among ordered aliases."""
    for alias in aliases:
        value = indexed.get(normalized_key(alias))
        if value is not None and clean_text(str(value)):
            return value
    return ""


def canonical_category(field: str, value: object) -> str:
    """Map an exact option or known synonym into the controlled vocabulary."""
    cleaned = clean_text(str(value))
    if not cleaned:
        return "Unknown" if field != "status" else "Not Verified"
    key = normalized_key(cleaned)
    for option in CATEGORY_OPTIONS[field]:
        if normalized_key(option) == key:
            return option
    return CATEGORY_SYNONYMS.get(field, {}).get(
        key, "Unknown" if field != "status" else "Not Verified"
    )


def stable_external_id(source: str, source_id: str, name: str, address: str) -> str:
    """Generate a reproducible cross-run ID without exposing the raw identifier."""
    seed = f"{source}|{source_id or name}|{address}"
    return "org_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def normalize_number(value: object) -> float | str:
    """Parse a coordinate-like value, returning blank for absent/invalid input."""
    cleaned = clean_text(str(value))
    if not cleaned:
        return ""
    try:
        return float(cleaned)
    except ValueError:
        return ""


def normalize_record(
    record: dict,
    source: str,
    field_map: dict[str, str] | None = None,
) -> dict:
    """Convert one source record into normalized and map-facing schema fields.

    Explicit field mappings take precedence over built-in aliases. For category
    values, a recognized source value wins; otherwise deterministic inference
    uses NTEE/name context and ultimately the schema's safe unknown default.
    Original category and verification text remains available for audit.
    """
    indexed = index_record(record)
    field_map = field_map or {}

    def value_for(field: str, aliases: dict[str, tuple[str, ...]]) -> object:
        """Resolve one field through an explicit override or its alias list."""
        explicit = field_map.get(field)
        if explicit:
            return indexed.get(normalized_key(explicit), "")
        return first_value(indexed, aliases.get(field, (field,)))

    output = {field: "" for field in SCHEMA_FIELDS}
    for field in FIELD_ALIASES:
        output[field] = clean_text(str(value_for(field, FIELD_ALIASES)))
    output["latitude"] = normalize_number(value_for("latitude", FIELD_ALIASES))
    output["longitude"] = normalize_number(value_for("longitude", FIELD_ALIASES))

    name = output["name"] or "Unnamed organization"
    output["name"] = name
    state = output["state"].upper()
    output["state"] = state

    source_category = clean_text(
        str(first_value(indexed, ("category", "categories", "classification", "ntee_label")))
    )
    ntee_code = clean_text(str(first_value(indexed, ("ntee_code", "ntee_cd", "ntee")))).upper()
    source_mapping = resolve_source_category(ntee_code, source_category)
    ntee_code = ntee_code or source_mapping["ntee_code"]
    inferred = gcc_classification(
        ntee_code,
        name,
        state,
        source_category=source_category,
    )

    # Canonicalize supplied categories before deciding whether inference is
    # needed. This prevents case variants from becoming duplicate UI filters.
    explicit_categories = {
        field: canonical_category(field, value_for(field, CATEGORY_INPUT_ALIASES))
        for field in CATEGORY_INPUT_ALIASES
    }

    organization_type = explicit_categories["organization_type"]
    if organization_type == "Unknown":
        organization_type, _ = infer_organization_type(name)

    audience = explicit_categories["audience_focus"]
    if audience == "Unknown":
        audience, _ = infer_audience(name, organization_type)

    climate_category = explicit_categories["climate_categories"]
    if climate_category == "Unknown":
        climate_category = inferred["climate_category"]

    action_category = explicit_categories["action_category"]
    if action_category == "Unknown":
        action_category = inferred["action_category"]

    resilience = explicit_categories["adaptation_vs_mitigation"]
    if resilience == "Unknown":
        resilience = inferred["resilience"]

    activity = explicit_categories["advocacy_vs_action"]
    if activity == "Unknown":
        activity = inferred["activity"]

    reach = explicit_categories["reach"]
    if reach == "Unknown":
        reach, _ = infer_reach(name, state, organization_type)

    verification = explicit_categories["status"]
    source_verification = clean_text(
        str(value_for("status", CATEGORY_INPUT_ALIASES))
    )

    # Generic schema names support interchange; gcc_* names are the stable map
    # interface. Both deliberately contain the same controlled value.
    output.update(
        {
            "organization_type": organization_type,
            "audience_focus": audience,
            "adaptation_vs_mitigation": resilience,
            "advocacy_vs_action": activity,
            "action_category": action_category,
            "climate_categories": climate_category,
            "reach": reach,
            "status": verification,
            "validated": verification == "Verified",
        }
    )

    source_id = clean_text(
        str(first_value(indexed, ("source_id", "id", "organization_id", "ein")))
    )
    output.update(
        {
            "id": stable_external_id(source, source_id, name, output["address"]),
            "source": source,
            "source_id": source_id,
            "source_category": source_category,
            "source_category_code": source_mapping["ntee_code"],
            "source_category_mapping_basis": source_mapping["mapping_basis"],
            "source_category_mapping_version": source_mapping["mapping_version"],
            "source_verification": source_verification,
            "ntee_code": ntee_code,
            "gcc_organization_type": organization_type,
            "gcc_audience_focus": audience,
            "gcc_resilience": resilience,
            "gcc_activity": activity,
            "gcc_action_category": action_category,
            "gcc_climate_category": climate_category,
            "gcc_reach": reach,
            "gcc_verification": verification,
            "schema_mapping_version": MAPPING_VERSION,
            "schema_mapping_method": (
                "recognized target value > shared NTEE/source-label crosswalk > "
                "ordered keyword rules > Unknown"
            ),
        }
    )
    return output


def read_records(path: Path) -> list[dict]:
    """Read supported tabular/JSON shapes into property dictionaries."""
    if path.suffix.casefold() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        return payload
    if payload.get("type") == "FeatureCollection":
        return [
            {**feature.get("properties", {}), **_geometry_fields(feature.get("geometry"))}
            for feature in payload.get("features", [])
        ]
    if isinstance(payload.get("records"), list):
        return payload["records"]
    raise ValueError("JSON input must be an array, FeatureCollection, or object with records")


def _geometry_fields(geometry: dict | None) -> dict:
    """Flatten valid GeoJSON Point coordinates into longitude/latitude fields."""
    if not geometry or geometry.get("type") != "Point":
        return {}
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) < 2:
        return {}
    return {"longitude": coordinates[0], "latitude": coordinates[1]}


def write_records(path: Path, records: list[dict]) -> None:
    """Write normalized CSV or JSON atomically with predictable field order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.suffix.casefold() == ".csv":
        preferred = ["id", *SCHEMA_FIELDS, "source", "source_id", "source_category",
                     "source_verification", "ntee_code", "gcc_organization_type",
                     "gcc_audience_focus", "gcc_resilience", "gcc_activity",
                     "gcc_action_category", "gcc_climate_category", "gcc_reach",
                     "gcc_verification", "schema_mapping_version", "schema_mapping_method"]
        extra = sorted({key for record in records for key in record}.difference(preferred))
        fieldnames = [*preferred, *extra]
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
    else:
        temporary.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    """Parse source paths, source identity, and optional column overrides."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source .csv or .json file")
    parser.add_argument("--output", type=Path, required=True, help="Normalized .csv or .json file")
    parser.add_argument("--source", required=True, help="Human-readable source name")
    parser.add_argument(
        "--field-map",
        type=Path,
        help="Optional JSON object mapping GCC field names to source column names",
    )
    return parser.parse_args()


def main() -> None:
    """Normalize all input records and report the applied mapping version."""
    args = parse_args()
    field_map = (
        json.loads(args.field_map.read_text(encoding="utf-8")) if args.field_map else None
    )
    source_records = read_records(args.input)
    normalized = [normalize_record(record, args.source, field_map) for record in source_records]
    write_records(args.output, normalized)
    print(f"Normalized {len(normalized):,} records to {args.output}")
    print(f"Mapping version: {MAPPING_VERSION}")


if __name__ == "__main__":
    main()
