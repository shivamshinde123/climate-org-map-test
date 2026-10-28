"""Regression tests for IRS selection, normalization, and schema crosswalking."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_irs_dataset import (
    build_dataset,
    clean_text,
    gcc_classification,
    stable_id,
)


class BuildIrsDatasetTests(unittest.TestCase):
    """Protect deterministic identities and the initial IRS-to-map contract."""

    def test_clean_text_collapses_whitespace(self):
        """Source whitespace is normalized without changing meaningful text."""
        self.assertEqual(clean_text("  CLIMATE   ACTION\tGROUP "), "CLIMATE ACTION GROUP")

    def test_ids_are_deterministic(self):
        """The same source identity always yields the same map identifier."""
        self.assertEqual(stable_id("irs", "123"), stable_id("irs", "123"))

    def test_gcc_crosswalk_uses_ntee_and_specific_name_keywords(self):
        """NTEE and ordered keywords resolve representative schema categories."""
        conservation = gcc_classification("C32", "Regional Wetlands Trust")
        self.assertEqual(conservation["climate_category"], "Conservation")
        self.assertEqual(conservation["action_category"], "Conservation")
        self.assertEqual(conservation["activity"], "Action")
        self.assertEqual(conservation["resilience"], "Unknown")

        food = gcc_classification("C99", "Community Food Waste and Compost Network")
        self.assertEqual(food["climate_category"], "Food & Food Waste")
        self.assertEqual(food["resilience"], "Unknown")
        self.assertIn("keyword", food["method"])

        municipal = gcc_classification("C20", "City of Worcester Environmental Commission", "MA")
        self.assertEqual(municipal["organization_type"], "Municipality")
        self.assertEqual(municipal["audience"], "Municipality")
        self.assertEqual(municipal["reach"], "Municipality")

    def test_build_filters_exact_codes_and_normalizes(self):
        """The builder emits only configured NTEE codes and complete base fields."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "Data"
            data_dir.mkdir()
            codes = root / "codes.txt"
            output = root / "app" / "data.geojson"
            codes.write_text("C20\nC30\n", encoding="utf-8")

            # Include one selected and one excluded row to exercise exact matching.
            fields = ["EIN", "NAME", "STREET", "CITY", "STATE", "ZIP", "NTEE_CD"]
            with (data_dir / "eo_ma.csv").open(
                "w", encoding="latin-1", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "EIN": "123",
                            "NAME": "  Local   Climate Group ",
                            "STREET": "1 Main St",
                            "CITY": "Worcester",
                            "STATE": "MA",
                            "ZIP": "01609",
                            "NTEE_CD": "C20",
                        },
                        {
                            "EIN": "456",
                            "NAME": "Not selected",
                            "STREET": "2 Main St",
                            "CITY": "Boston",
                            "STATE": "MA",
                            "ZIP": "02108",
                            "NTEE_CD": "A20",
                        },
                    ]
                )

            stats = build_dataset(data_dir, codes, output)
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(stats.source_rows, 2)
            self.assertEqual(stats.emitted, 1)
            self.assertEqual(payload["metadata"]["record_count"], 1)
            feature = payload["features"][0]
            self.assertEqual(feature["properties"]["name"], "Local Climate Group")
            self.assertEqual(feature["properties"]["ntee_code"], "C20")
            self.assertIsNone(feature["geometry"])
            self.assertEqual(feature["properties"]["location_precision"], "ungeocoded")
            self.assertEqual(feature["properties"]["gcc_climate_category"], "Environmental")
            self.assertEqual(feature["properties"]["gcc_organization_type"], "Nonprofit / Grassroots")
            self.assertEqual(feature["properties"]["gcc_verification"], "Not Verified")
            self.assertNotIn("validated", feature["properties"])
            self.assertNotIn("status", feature["properties"])
            self.assertNotIn("organization_type", feature["properties"])
            self.assertNotIn("climate_categories", feature["properties"])
            self.assertNotIn("action_category", feature["properties"])
            self.assertNotIn("adaptation_vs_mitigation", feature["properties"])
            self.assertNotIn("gcc_mapping_version", feature["properties"])
            self.assertEqual(
                feature["properties"]["irs_category"],
                "C20 - Pollution Abatement and Control",
            )


if __name__ == "__main__":
    unittest.main()
