"""Tests for orchestration safeguards that make pipeline reruns inexpensive."""

import json
import tempfile
import unittest
from pathlib import Path

from main import dataset_has_complete_coordinates, load_enrichment_overlay, restore_enrichment


class MainPipelineTests(unittest.TestCase):
    """Protect coordinate reuse and preservation of paid enrichment fields."""

    def test_complete_coordinates_are_reusable(self):
        """Owned points and final no-point records do not require geocoding again."""
        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-71.5, 43.7]},
                    "properties": {"location_precision": "zip_level_fallback"},
                },
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {"location_precision": "unavailable"},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "organizations.geojson"
            path.write_text(json.dumps(collection), encoding="utf-8")
            self.assertTrue(dataset_has_complete_coordinates(path))

    def test_rebuild_preserves_paid_website_and_jev_enrichment(self):
        """Rebuilding deterministic base data restores prior enrichment by ID."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "organizations.geojson"
            enriched = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "id": "org_1",
                        "website_url": "https://example.org/",
                        "summary": "Evidence-based summary.",
                        "jev_classification_status": "classified",
                        "gcc_activity": "Advocacy",
                        "advocacy_vs_action": "Advocacy",
                    },
                }],
            }
            path.write_text(json.dumps(enriched), encoding="utf-8")
            overlay = load_enrichment_overlay(path)

            rebuilt = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "id": "org_1",
                        "website_url": "",
                        "summary": "",
                        "gcc_activity": "Unknown",
                        "advocacy_vs_action": "Unknown",
                    },
                }],
            }
            path.write_text(json.dumps(rebuilt), encoding="utf-8")
            restored = restore_enrichment(path, overlay)
            result = json.loads(path.read_text(encoding="utf-8"))
            properties = result["features"][0]["properties"]

        self.assertEqual(restored, 1)
        self.assertEqual(properties["website_url"], "https://example.org/")
        self.assertEqual(properties["gcc_activity"], "Advocacy")


if __name__ == "__main__":
    unittest.main()
