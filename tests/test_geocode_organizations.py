"""Tests for address caching, Census parsing, and labeled fallback geometry."""

import unittest

from scripts.geocode_organizations import (
    apply_fallback,
    apply_result,
    make_address_key,
    parse_batch_response,
)


class GeocodeOrganizationTests(unittest.TestCase):
    """Protect geocoder ownership of coordinates and precision provenance."""

    def setUp(self):
        """Create a feature with placeholder geometry for mutation-focused tests."""
        self.feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-71.0, 42.0]},
            "properties": {
                "id": "org_1",
                "address": "4600 Silver Hill Rd",
                "city": "Washington",
                "state": "DC",
                "postal_code": "20233",
                "latitude": 42.0,
                "longitude": -71.0,
                "notes": "placeholder",
            },
        }

    def test_address_key_is_normalized(self):
        """Cosmetic street formatting does not invalidate a cached result."""
        other = {"properties": dict(self.feature["properties"])}
        other["properties"]["address"] = "  4600   silver hill rd "
        self.assertEqual(
            make_address_key(self.feature["properties"]),
            make_address_key(other["properties"]),
        )

    def test_fallback_prefers_zip_then_city_then_no_point(self):
        """ZIP beats city, scatter stays tight and repeatable, and no match means no point."""
        zips = {"20233": (38.846, -76.927)}
        cities = {("WASHINGTON", "DC"): (38.9, -77.0)}

        self.assertTrue(apply_fallback(self.feature, cities, zips))
        self.assertEqual(self.feature["properties"]["location_precision"], "zip_level_fallback")
        first = list(self.feature["geometry"]["coordinates"])
        longitude, latitude = first
        self.assertLess(abs(latitude - 38.846), 0.006)
        self.assertLess(abs(longitude - -76.927), 0.006 / 0.7)
        apply_fallback(self.feature, cities, zips)
        self.assertEqual(self.feature["geometry"]["coordinates"], first)

        self.assertTrue(apply_fallback(self.feature, cities, {}))
        self.assertEqual(self.feature["properties"]["location_precision"], "city_level_fallback")

        self.assertFalse(apply_fallback(self.feature, {}, {}))
        self.assertIsNone(self.feature["geometry"])
        self.assertEqual(self.feature["properties"]["location_precision"], "unavailable")

    def test_parse_and_apply_match(self):
        """A valid Census CSV row becomes Point geometry with provider metadata."""
        self.feature["geometry"] = None
        response = (
            '"org_1","4600 Silver Hill Rd, Washington, DC, 20233",'
            '"Match","Exact","4600 SILVER HILL RD, WASHINGTON, DC, 20233",'
            '"-76.92744,38.84599","12345","L"\n'
        )
        result = parse_batch_response(
            response, {"org_1": self.feature}, "2026-09-27T00:00:00+00:00"
        )["org_1"]
        self.assertTrue(apply_result(self.feature, result))
        self.assertEqual(self.feature["geometry"]["coordinates"], [-76.92744, 38.84599])
        self.assertEqual(
            self.feature["properties"]["location_precision"],
            "census_address_range",
        )

    def test_unmatched_result_keeps_existing_coordinates(self):
        """An unusable result reports failure without silently erasing geometry."""
        response = '"org_1","Unknown","No_Match","","","","",""\n'
        result = parse_batch_response(
            response, {"org_1": self.feature}, "2026-09-27T00:00:00+00:00"
        )["org_1"]
        self.assertFalse(apply_result(self.feature, result))
        self.assertEqual(self.feature["geometry"]["coordinates"], [-71.0, 42.0])
        self.assertEqual(self.feature["properties"]["geocoding_status"], "No_Match")


if __name__ == "__main__":
    unittest.main()

