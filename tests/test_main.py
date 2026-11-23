"""Tests for orchestration safeguards that make pipeline reruns inexpensive."""

import unittest

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
        self.assertTrue(dataset_has_complete_coordinates(collection))

    def test_rebuild_preserves_paid_website_and_jev_enrichment(self):
        """Rebuilding deterministic base data restores prior enrichment by ID."""
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
        overlay = load_enrichment_overlay(enriched)

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
        restored = restore_enrichment(rebuilt, overlay)
        properties = rebuilt["features"][0]["properties"]

        self.assertEqual(restored, 1)
        self.assertEqual(properties["website_url"], "https://example.org/")
        self.assertEqual(properties["gcc_activity"], "Advocacy")


if __name__ == "__main__":
    unittest.main()
