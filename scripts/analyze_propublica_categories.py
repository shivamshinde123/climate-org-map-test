"""Compare IRS EO BMF fields, ProPublica fields, and the map's target schema.

This analyzer does not pretend that a source field is a target classification.
It measures exact field agreement, inventories what ProPublica actually returns,
and writes an auditable CSV plus a JSON summary for the research report.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from category_crosswalk import DEFAULT_CROSSWALK_PATH, resolve_source_category
    from propublica_common import DEFAULT_DATA_DIR, DEFAULT_INPUT, feature_ein, first_present, iter_geojson_features
except ModuleNotFoundError:  # Package-style import used by tests and tooling.
    from scripts.category_crosswalk import DEFAULT_CROSSWALK_PATH, resolve_source_category
    from scripts.propublica_common import (
        DEFAULT_DATA_DIR,
        DEFAULT_INPUT,
        feature_ein,
        first_present,
        iter_geojson_features,
    )


def normalized_code(value: Any) -> str:
    """Normalize category codes for comparison without inventing a mapping."""

    return str(value or "").strip().upper()


def normalized_subsection(value: Any) -> str:
    """Normalize equivalent subsection representations such as ``03`` and ``3``."""

    text = normalized_code(value)
    return str(int(text)) if text.isdigit() else text


def form_type_label(value: Any) -> str:
    """Translate ProPublica's documented form codes without treating zero as missing."""

    labels = {0: "990", 1: "990-EZ", 2: "990-PF"}
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    return labels.get(numeric, f"UNKNOWN ({numeric})")


def analyze(input_path: Path, data_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join cached API records to local features and calculate agreement stats."""

    local_by_ein = {feature_ein(feature): feature for feature in iter_geojson_features(input_path)}
    rows: list[dict[str, Any]] = []
    field_presence: Counter[str] = Counter()
    form_types: Counter[str] = Counter()
    crosswalk_path = data_dir / "category-crosswalk.json"
    if not crosswalk_path.exists():
        crosswalk_path = DEFAULT_CROSSWALK_PATH

    for response_path in sorted((data_dir / "raw").glob("*.json")):
        payload = json.loads(response_path.read_text(encoding="utf-8"))
        organization = payload.get("organization") or {}
        ein = "".join(character for character in str(first_present(organization, "ein", "strein") or "") if character.isdigit()).zfill(9)
        feature = local_by_ein.get(ein, {})
        local = feature.get("properties") or {}

        for field, value in organization.items():
            if value not in (None, "", [], {}):
                field_presence[field] += 1
        filings = payload.get("filings_with_data") or []
        for filing in filings:
            form_types[form_type_label(filing.get("formtype"))] += 1

        irs_ntee = normalized_code(
            first_present(
                local,
                "ntee_code",
                "NTEE_CD",
                "raw_ntee_code",
                "source_ntee_code",
                "ntee",
            )
        )
        pp_ntee = normalized_code(first_present(organization, "raw_ntee_code", "ntee_code"))
        irs_subsection = normalized_subsection(
            first_present(
                local,
                "subsection",
                "SUBSECTION",
                "subseccd",
                "subsection_code",
                "source_subsection",
            )
        )
        pp_subsection = normalized_subsection(first_present(organization, "subseccd", "subsection_code"))
        # Prefer the local BMF code so the comparison does not silently replace
        # the project's source snapshot with a newer ProPublica snapshot.  If
        # local NTEE is absent, the ProPublica value is an explicitly visible
        # fallback rather than an implied match.
        mapping_code = irs_ntee or pp_ntee
        target = resolve_source_category(
            mapping_code,
            first_present(organization, "ntee_code", "raw_ntee_code"),
            crosswalk_path=crosswalk_path,
        )
        rows.append(
            {
                "ein": ein,
                "irs_name": first_present(local, "name", "NAME"),
                "propublica_name": organization.get("name"),
                "irs_ntee": irs_ntee,
                "propublica_ntee": pp_ntee,
                "ntee_exact_match": bool(irs_ntee and pp_ntee and irs_ntee == pp_ntee),
                "irs_subsection": irs_subsection,
                "propublica_subsection": pp_subsection,
                "subsection_exact_match": bool(irs_subsection and pp_subsection and irs_subsection == pp_subsection),
                "filings_with_data": len(filings),
                "filings_without_data": len(payload.get("filings_without_data") or []),
                "latest_form_type": form_type_label(filings[0].get("formtype")) if filings else None,
                "latest_tax_period": filings[0].get("tax_prd") if filings else None,
                "target_climate_candidate": target["climate_category"],
                "target_action_candidate": target["action_category"],
                "target_activity_candidate": target["activity"],
                "target_resilience_candidate": target["resilience"],
                "target_organization_type": "Unknown",
                "target_audience_focus": "Unknown",
                "target_reach": "Unknown",
                "target_verification": "Not Verified",
                "target_mapping_basis": target["mapping_basis"],
                "target_mapping_version": target["mapping_version"],
            }
        )

    total = len(rows)
    ntee_counts = Counter(row["irs_ntee"] or row["propublica_ntee"] or "UNKNOWN" for row in rows)
    target_candidate_counts = {
        field: dict(Counter(row[field] for row in rows).most_common())
        for field in (
            "target_climate_candidate",
            "target_action_candidate",
            "target_activity_candidate",
            "target_resilience_candidate",
        )
    }
    summary = {
        "cached_organizations_analyzed": total,
        "ntee_present_in_both": sum(bool(row["irs_ntee"] and row["propublica_ntee"]) for row in rows),
        "ntee_exact_matches": sum(row["ntee_exact_match"] for row in rows),
        "subsection_present_in_both": sum(bool(row["irs_subsection"] and row["propublica_subsection"]) for row in rows),
        "subsection_exact_matches": sum(row["subsection_exact_match"] for row in rows),
        "organizations_with_structured_filings": sum(row["filings_with_data"] > 0 for row in rows),
        "organizations_without_structured_filings": sum(row["filings_with_data"] == 0 for row in rows),
        "ntee_counts": dict(ntee_counts.most_common()),
        "target_candidate_counts": target_candidate_counts,
        "ntee_mismatch_eins": [row["ein"] for row in rows if row["irs_ntee"] and row["propublica_ntee"] and not row["ntee_exact_match"]],
        "subsection_mismatch_eins": [row["ein"] for row in rows if row["irs_subsection"] and row["propublica_subsection"] and not row["subsection_exact_match"]],
        "organization_field_presence": dict(field_presence.most_common()),
        "filing_form_types": dict(form_types.most_common()),
    }
    return rows, summary


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any], data_dir: Path) -> None:
    """Write machine-readable comparison artifacts beside the raw cache."""

    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / "irs-propublica-comparison.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (data_dir / "analysis-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    comparison_rows, analysis_summary = analyze(args.input, args.data_dir)
    write_outputs(comparison_rows, analysis_summary, args.data_dir)
    print(json.dumps(analysis_summary, indent=2))
