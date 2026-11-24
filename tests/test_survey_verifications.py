"""Survey-verified organizations keep their own answers: Jev is skipped for them."""

import unittest

from scripts.enrich_organizations_with_jev import (
    CONTACT_VERSION, DISCOVERY_VERSION, enrichment_is_complete, is_survey_verified,
)


class SurveyVerificationTests(unittest.TestCase):
    def test_survey_verified_record_needs_no_jev_result(self):
        properties = {"verification_source": "GCC survey (gb_survey): answered itself", "gcc_reach": "Town / City"}
        self.assertTrue(is_survey_verified(properties))
        self.assertFalse(is_survey_verified({"verification_source": "Admin portal"}))
        properties.update(website_discovery_version=DISCOVERY_VERSION, website_discovery_model="m",
                          website_discovery_status="found", contact_version=CONTACT_VERSION)
        self.assertTrue(enrichment_is_complete(properties, "m", "jev"))

    def test_brave_query_drops_legal_suffix_and_chamber_pages_are_directories(self):
        from scripts.website_discovery import brave_query, domain_is_exact_name, is_directory
        self.assertEqual(brave_query({"name": "BOSTON HARBOR NOW INC", "city": "BOSTON", "state": "MA"}), "BOSTON HARBOR NOW BOSTON MA")
        self.assertEqual(brave_query({"name": "E INC", "city": "BOSTON", "state": "MA"}), "E INC BOSTON MA")
        self.assertTrue(is_directory("https://business.clintonareachamber.org/list/member/x"))
        self.assertTrue(domain_is_exact_name("https://www.bostonharbornow.org/", "BOSTON HARBOR NOW INC", "BOSTON"))
        self.assertFalse(domain_is_exact_name("https://davisfarmland.com/", "FARMLAND CONSERVANCY INC", "DRACUT"))
        self.assertFalse(domain_is_exact_name("https://www.marblehead.org/", "MARBLEHEAD CONSERVANCY INC", "MARBLEHEAD"))


if __name__ == "__main__":
    unittest.main()
