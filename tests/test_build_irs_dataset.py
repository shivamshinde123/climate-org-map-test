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
        # The GCC schema has no Conservation climate category; it is Environmental.
        self.assertEqual(conservation["climate_category"], "Environmental")
        self.assertEqual(conservation["action_category"], "Conservation")
        self.assertEqual(conservation["activity"], "Action")
        self.assertEqual(conservation["resilience"], "Unknown")

        # GCC schema reach has no Global or Municipality, and type has no Government-affiliated.
        self.assertEqual(gcc_classification("C01", "Global Climate Alliance")["reach"], "State / National")
        town = gcc_classification("C01", "Town of Acton")
        self.assertEqual((town["organization_type"], town["reach"]), ("Municipality", "Town / City"))
        self.assertEqual(gcc_classification("C01", "Water Authority")["organization_type"], "Municipality")

        food = gcc_classification("C99", "Community Food Waste and Compost Network")
        self.assertEqual(food["climate_category"], "Food & Food Waste")
        self.assertEqual(food["resilience"], "Unknown")
        self.assertIn("keyword", food["method"])

        municipal = gcc_classification("C20", "City of Worcester Environmental Commission", "MA")
        self.assertEqual(municipal["organization_type"], "Municipality")
        self.assertEqual(municipal["audience"], "Municipality")
        self.assertEqual(municipal["reach"], "Town / City")

    def test_build_filters_exact_codes_and_normalizes(self):
        """The builder emits only configured NTEE codes and complete base fields."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "Data"
            data_dir.mkdir()
            codes = root / "codes.txt"
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

            payload, stats = build_dataset(data_dir, codes)

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


class DownloadIrsFilesTests(unittest.TestCase):
    def test_downloads_new_skips_unchanged_and_keeps_local_copy_on_failure(self):
        import io
        import urllib.error
        from unittest import mock

        from scripts import build_irs_dataset as module

        def fake_urlopen(request, timeout):
            state = request.full_url.rsplit("_", 1)[1][:2]
            if state == "ak":  # new on irs.gov
                return io.BytesIO(b"EIN,NAME")
            if state == "al":  # unchanged since the local copy
                assert request.get_header("If-modified-since")
                raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, None)
            raise urllib.error.URLError("offline")

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(module, "IRS_STATES", ["ak", "al", "ar"]), \
                mock.patch.object(module.urllib.request, "urlopen", fake_urlopen):
            folder = Path(directory)
            (folder / "eo_al.csv").write_text("old", encoding="utf-8")
            (folder / "eo_ar.csv").write_text("old", encoding="utf-8")
            self.assertEqual(module.download_irs_files(folder), 1)
            self.assertEqual((folder / "eo_ak.csv").read_text(encoding="utf-8"), "EIN,NAME")
            self.assertEqual((folder / "eo_ar.csv").read_text(encoding="utf-8"), "old")
            (folder / "eo_ar.csv").unlink()
            with self.assertRaises(urllib.error.URLError):  # no local copy to fall back on
                module.download_irs_files(folder)


if __name__ == "__main__":
    unittest.main()
