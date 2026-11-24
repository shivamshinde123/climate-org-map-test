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
                    "email": "info@example.org",
                    "phone": "(617) 555-0100",
                    "contact_version": "gcc-contacts-v3",
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
                    "email": "",
                    "phone": "",
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
        # Contacts survive too (a rebuild used to blank every email and phone).
        self.assertEqual((properties["email"], properties["phone"]), ("info@example.org", "(617) 555-0100"))
        self.assertEqual(properties["contact_version"], "gcc-contacts-v3")
        # The IRS-derived categories Jev replaced come from the rebuilt record.
        self.assertEqual(properties["pre_enrichment_categories"]["gcc_activity"], "Unknown")


if __name__ == "__main__":
    unittest.main()
