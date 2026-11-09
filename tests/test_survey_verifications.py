"""Survey verification is matched on EIN and only touches listed organizations."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.survey_verifications import apply_survey_verifications


class SurveyVerificationTests(unittest.TestCase):
    def test_marks_only_matching_ein(self):
        features = [
            {"properties": {"source_id": "871173877", "gcc_verification": "Not Verified", "status": None}},
            {"properties": {"source_id": "123456789", "gcc_verification": "Not Verified"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            path.write_text(json.dumps([{"ein": "871173877", "survey": "gb_survey", "evidence": "answered itself"}]))
            self.assertEqual(apply_survey_verifications(features, path), 1)
        self.assertEqual(features[0]["properties"]["gcc_verification"], "Verified")
        self.assertTrue(features[0]["properties"]["validated"])
        self.assertEqual(features[1]["properties"]["gcc_verification"], "Not Verified")

    def test_survey_organizations_are_verified_town_pins_and_idempotent(self):
        from scripts.survey_organizations import add_survey_organizations
        with tempfile.TemporaryDirectory() as directory:
            rows = Path(directory) / "orgs.csv"
            rows.write_text(
                "name,city,state,website_url,organization_type,audience_focus,adaptation_vs_mitigation,"
                "advocacy_vs_action,climate_categories,reach,survey,row_uuid,address,postal_code,latitude,longitude\n"
                "Green Newton,Newton,MA,https://greennewton.org,Nonprofit / Grassroots,Residents,Mitigation,"
                "Both,Energy Efficiency,Town / City,andover_survey,u-1,,,,\n"
                "350 MetroNorth,Somerville,MA,,,,,,,,,u-2,15 Properzi Way,02143,42.38,-71.10\n",
                encoding="utf-8",
            )
            centroids = Path(directory) / "cities.csv"
            centroids.write_text("city,state,latitude,longitude\nNEWTON,MA,42.33,-71.21\n", encoding="utf-8")
            payload = {"features": [{"properties": {"source": "IRS EO BMF", "name": "X"}}]}
            self.assertEqual(add_survey_organizations(payload, rows, centroids), 2)
            self.assertEqual(add_survey_organizations(payload, rows, centroids), 2)
        self.assertEqual(len(payload["features"]), 3)  # replaced, not duplicated
        org, exact = payload["features"][1], payload["features"][2]
        self.assertEqual(org["properties"]["gcc_verification"], "Verified")
        self.assertEqual(org["properties"]["location_precision"], "city_level_fallback")  # no address -> town
        lng, lat = org["geometry"]["coordinates"]
        self.assertLess(abs(lat - 42.33), 0.006)
        self.assertEqual(exact["properties"]["address"], "15 Properzi Way")  # survey address is used as-is
        self.assertEqual(exact["properties"]["location_precision"], "census_address_range")
        self.assertEqual(exact["geometry"]["coordinates"], [-71.10, 42.38])

    def test_survey_answers_replace_categories_and_skip_jev(self):
        from scripts.enrich_organizations_with_jev import CONTACT_VERSION, DISCOVERY_VERSION, enrichment_is_complete
        properties = {"source_id": "871173877", "gcc_reach": "State / National", "gcc_resilience": "Mitigation"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            path.write_text(json.dumps([{"ein": "871173877", "survey": "gb", "evidence": "x",
                                         "survey_categories": {"reach": "Town / City"}}]))
            apply_survey_verifications([{"properties": properties}], path)
        self.assertEqual(properties["gcc_reach"], "Town / City")  # survey answer wins
        self.assertEqual(properties["gcc_resilience"], "Mitigation")  # unanswered question kept
        properties.update(website_discovery_version=DISCOVERY_VERSION, website_discovery_model="m",
                          website_discovery_status="found", contact_version=CONTACT_VERSION)
        self.assertTrue(enrichment_is_complete(properties, "m", "jev"))  # no Jev result needed

    def test_missing_file_changes_nothing(self):
        self.assertEqual(apply_survey_verifications([], Path("does-not-exist.json")), 0)


if __name__ == "__main__":
    unittest.main()
