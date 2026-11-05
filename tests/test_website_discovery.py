"""Regression tests built from the 2026-11-05 Alaska pilot's bad results."""

import unittest

from scripts.website_discovery import (
    _extract_contacts,
    _HTMLParser,
    clean_text,
    decode_cfemail,
    domain_matches_name,
    email_matches_site,
    is_directory,
    is_homepage_like,
)


class WebsiteDiscoveryTests(unittest.TestCase):
    def test_directory_pages_are_not_official_sites(self):
        self.assertTrue(is_directory("https://getholdings.com/nonprofits/ein/202860877"))
        self.assertTrue(is_directory("https://greatnonprofits.org/org/alaskans-for-palmer-hay-flats"))
        self.assertTrue(is_directory("https://www.causeiq.com/organizations/x,123/"))
        self.assertTrue(is_directory("https://some-new-site.com/ein/123456789"))
        self.assertTrue(is_directory("https://dnr.alaska.gov/ag/BAC/AFTC030410.pdf"))
        self.assertFalse(is_directory("https://www.friendsoftheccsc.com/"))
        self.assertFalse(is_directory("https://aoos.org/"))
        self.assertFalse(is_directory("https://wwf.org/"))  # old lstrip("www.") bug ate leading w's
        # Wrong "websites" from the Rhode Island run.
        self.assertTrue(is_directory("https://business.sos.ri.gov/CorpWeb/CorpSearch/CorpSummary.aspx?FEIN=1"))
        self.assertTrue(is_directory("https://www.govinfo.gov/app/details/USCOURTS-rid-1_20-cv-00355"))
        self.assertTrue(is_directory("https://www.npsri.net/site/default.aspx?FlexDataID=1032&PageID=71"))
        self.assertTrue(is_directory("https://www.philanthropy.org/grant/x"))
        self.assertTrue(is_directory("https://ecori.org/wildlife-news/feed/"))

    def test_own_domain_and_homepage_signals(self):
        cases = [
            ("BURRILLVILLE LAND TRUST", "https://www.burrillvillelandtrust.org/", True),
            ("WEST BAY LAND TR", "https://westbaylandtrust.org/", True),
            ("SOUTH KINGSTOWN LAND TRUST", "https://sklt.org/who-we-are/", True),
            ("FRIENDS OF GREEN HILL POND", "https://foghp.org/", True),
            ("LAKE MISHNOCK PRESERVATION ASSOCIATION INC", "https://lakemishnock.org/", True),
            ("WOONASQUATUCKET RIVER WATERSHED COUNCIL", "https://volunteer.uwri.org/agency/", False),
            ("CLEAN OCEAN ACCESS", "https://ecori.org/small-but-mighty", False),
            ("STEWARDS OF THE GLEN", "https://www.actionnetwork.org/", False),
            ("RHODE ISLAND ENVIROTHON INC", "https://www.rieea.org/resource/x", False),
            ("THE RHODE ISLAND ASSOCIATION OF CONSERVATION DISTRICTS", "https://www.riacd.org/", True),
        ]
        for name, url, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(domain_matches_name(url, name), expected)
        self.assertTrue(is_homepage_like("https://ribike.org/"))
        self.assertTrue(is_homepage_like("https://sklt.org/who-we-are/"))
        self.assertFalse(is_homepage_like("https://ecori.org/small-but-mighty-nonprofit-clean-ocean-access/"))
        self.assertFalse(is_homepage_like("https://example.org/a/b/"))

    def test_contacts_must_belong_to_the_site(self):
        self.assertTrue(email_matches_site("info@akfarmland.com", "https://akfarmland.com/"))
        self.assertTrue(email_matches_site("info@aoos.org", "https://www.aoos.org/"))
        self.assertTrue(email_matches_site("greengroup@gmail.com", "https://greengroup.org/"))
        self.assertFalse(email_matches_site("support@greatnonprofits.org", "https://akfarmland.com/"))
        self.assertFalse(email_matches_site("[email protected]", "https://caves.org/"))

    def test_cloudflare_hidden_email_is_decoded(self):
        key = 0x2A
        encoded = f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in "info@grotto.org")
        self.assertEqual(decode_cfemail(encoded), "info@grotto.org")
        html_text = f'<a href="/cdn-cgi/l/email-protection#{encoded}">[email protected]</a>'
        self.assertEqual(_extract_contacts(html_text, "https://grotto.org/")["email"], "info@grotto.org")

    def test_summary_text_is_clean(self):
        self.assertEqual(clean_text("NOAA�s <strong>IOOS</strong> &amp; partners"), "NOAAs IOOS & partners")
        parser = _HTMLParser()
        parser.feed("<p>Home</p><script>var x = 1;</script><p>" + "We restore salt marshes. " * 5 + "</p>")
        self.assertTrue(parser.first_paragraph.startswith("We restore salt marshes."))
        self.assertNotIn("var x", parser.text)


if __name__ == "__main__":
    unittest.main()
