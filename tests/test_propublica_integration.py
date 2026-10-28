"""Focused unit tests for deterministic selection and category comparison."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from scripts.analyze_propublica_categories import analyze
from scripts.propublica_common import normalize_ein


def test_normalize_ein_handles_common_source_representations() -> None:
    assert normalize_ein("12-3456789") == "123456789"
    assert normalize_ein(12345678) == "012345678"
    assert normalize_ein("123456789.0") == "123456789"
    assert normalize_ein(None) == ""
    assert normalize_ein("1234567890") == ""


def test_analyzer_compares_bmf_and_propublica_without_inventing_categories(tmp_path: Path) -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": None,
                "properties": {
                    "source_id": "12-3456789",
                    "name": "Example Climate Group",
                    "ntee_code": "C35",
                    "subsection": "03",
                },
            }
        ],
    }
    input_path = tmp_path / "organizations.geojson"
    input_path.write_text(json.dumps(geojson), encoding="utf-8")
    raw_dir = tmp_path / "propublica" / "raw"
    raw_dir.mkdir(parents=True)
    response = {
        "organization": {
            "ein": 123456789,
            "name": "EXAMPLE CLIMATE GROUP",
            "raw_ntee_code": "C35",
            "subseccd": "03",
        },
        "filings_with_data": [{"formtype": 0, "tax_prd": 202312}],
        "filings_without_data": [],
    }
    (raw_dir / "123456789.json").write_text(json.dumps(response), encoding="utf-8")

    rows, summary = analyze(input_path, raw_dir.parent)

    assert rows[0]["ntee_exact_match"] is True
    assert rows[0]["subsection_exact_match"] is True
    assert rows[0]["latest_form_type"] == "990"
    assert rows[0]["target_climate_candidate"] == "Energy Efficiency"
    assert rows[0]["target_action_candidate"] == "Conservation"
    assert rows[0]["target_activity_candidate"] == "Action"
    assert rows[0]["target_resilience_candidate"] == "Mitigation"
    assert rows[0]["target_mapping_basis"] == "IRS/ProPublica NTEE C35"
    assert rows[0]["target_mapping_version"] == "2.0.0"
    assert summary["organizations_with_structured_filings"] == 1
    assert summary["filing_form_types"] == {"990": 1}
    assert "climate_category" not in summary["organization_field_presence"]
