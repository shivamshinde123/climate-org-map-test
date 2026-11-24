"""Tests for address caching, Census parsing, and labeled fallback geometry."""

import unittest

from scripts.geocode_organizations import (
    GeocodeResult,
    apply_fallback,
    apply_result,
    make_address_key,
    match_city,
    load_cache,
    parse_batch_response,
    save_cache,
)
from tests.fake_store import FakeStore


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

    def test_city_matching_survives_irs_truncation_and_census_naming(self):
        """IRS 13-character abbreviations still find the right Census place, and nothing wrong."""
        cities = {
            ("CHARLOTTESVILLE", "VA"): (1, 1), ("COLORADO SPRINGS", "CO"): (2, 2),
            ("BOISE CITY", "ID"): (3, 3), ("ST. LOUIS", "MO"): (4, 4), ("NEW YORK", "NY"): (5, 5),
            ("WATERSMEET", "MI"): (6, 6), ("CLEARBROOK", "NJ"): (7, 7), ("CARSON", "NV"): (8, 8),
        }
        self.assertEqual(match_city("CHARLOTTESVLE", "VA", cities), (1, 1))
        self.assertEqual(match_city("COLORADO SPGS", "CO", cities), (2, 2))
        self.assertEqual(match_city("BOISE", "ID", cities), (3, 3))
        self.assertEqual(match_city("SAINT LOUIS", "MO", cities), (4, 4))
        self.assertEqual(match_city("BROOKLYN", "NY", cities), (5, 5))
        self.assertEqual(match_city("CARSON CITY", "NV", cities), (8, 8))
        self.assertIsNone(match_city("WATERS", "MI", cities))
        self.assertIsNone(match_city("CEDAR BROOK", "NJ", cities))
        self.assertIsNone(match_city("CHARLOTTESVLE", "MD", cities))

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

    def test_cache_round_trip_keys_results_by_organization_id(self):
        fake = FakeStore(self)
        result = GeocodeResult("org_1", "key", "Match", "Exact", "1 MAIN ST", "-71.0", "42.0", "9", "L")
        save_cache({"org_1": result})
        self.assertNotIn("id", fake.caches["census"]["org_1"])
        self.assertEqual(load_cache(), {"org_1": result})


if __name__ == "__main__":
    unittest.main()

