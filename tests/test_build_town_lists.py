"""Tests for the town-list builder (no network)."""

import unittest

from scripts.build_town_lists import clean, town_lists


class TownListTests(unittest.TestCase):
    def test_census_type_words_are_removed(self):
        self.assertEqual(clean("Beverly city"), "Beverly")
        self.assertEqual(clean("Abanda CDP"), "Abanda")
        self.assertEqual(clean("Manchester-by-the-Sea town"), "Manchester-by-the-Sea")
        self.assertEqual(clean("Agawam Town city", "MA"), "Agawam")
        self.assertEqual(clean("Charles Town city", "WV"), "Charles Town")

    def test_only_governing_municipal_subdivisions_are_added(self):
        places = [{"USPS": "MA", "NAME": "Boston city"}]
        cousubs = [
            {"USPS": "MA", "NAME": "Andover town", "FUNCSTAT": "A"},
            {"USPS": "MA", "NAME": "Boston city", "FUNCSTAT": "A"},
            {"USPS": "ME", "NAME": "District 1", "FUNCSTAT": "A"},
            {"USPS": "AL", "NAME": "Abbeville CCD", "FUNCSTAT": "S"},
        ]
        self.assertEqual(town_lists(places, cousubs), {"MA": ["Andover", "Boston"]})


if __name__ == "__main__":
    unittest.main()
