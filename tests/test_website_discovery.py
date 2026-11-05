"""Regression tests built from the 2026-11-05 Alaska pilot's bad results."""

import unittest

from scripts.website_discovery import (
    _extract_contacts,
    _HTMLParser,
    choose_summary,
    clean_text,
    crawl_for_contacts,
    normalize_phone,
    tidy_summary,
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
        self.assertFalse(is_homepage_like("https://juneau-alaska.alaskaadvisor.com/bootlegger.html"))
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

    def test_phone_numbers_are_validated_and_must_be_labelled(self):
        self.assertEqual(normalize_phone("907.267.1247"), "(907) 267-1247")
        self.assertEqual(normalize_phone("+1 (401) 555-0182"), "(401) 555-0182")
        self.assertEqual(normalize_phone("123-456-7890"), "")  # area code can't start with 1
        page = ("<p>Fax: 401-555-0100</p><p>Our trail volunteers logged 4015550199 hours</p>"
                "<p>Office phone: (401) 555-0123</p>")
        self.assertEqual(_extract_contacts(page, "https://example.org/")["phone"], "(401) 555-0123")
        self.assertEqual(_extract_contacts('<a href="tel:+14015550111">Call</a>', "https://example.org/")["phone"],
                         "(401) 555-0111")
        # One unlabelled footer number is the org's; several unlabelled numbers are ambiguous.
        self.assertEqual(_extract_contacts("<p>Newport Tree Conservancy 401-324-9204</p>", "https://x.org/")["phone"],
                         "(401) 324-9204")
        roster = "<p>President Jane Doe 401-486-5174 Treasurer John Roe 401-527-2802</p>"
        self.assertEqual(_extract_contacts(roster, "https://x.org/")["phone"], "")

    def test_page_on_a_shared_host_gets_no_contacts(self):
        """caves.org/grotto/x carried the national society's phone, not the grotto's."""
        contacts = crawl_for_contacts("https://caves.org/grotto/glacier-grotto/")
        self.assertEqual((contacts["email"], contacts["phone"]), ("", ""))
        self.assertTrue(contacts["accessible"])  # no paid fallback for it either

    def test_summary_text_is_clean(self):
        self.assertEqual(clean_text("NOAA�s <strong>IOOS</strong> &amp; partners"), "NOAAs IOOS & partners")
        parser = _HTMLParser()
        parser.feed("<p>Home</p><script>var x = 1;</script><p>" + "We restore salt marshes. " * 5 + "</p>")
        self.assertTrue(parser.paragraphs[-1].startswith("We restore salt marshes."))
        self.assertNotIn("var x", parser.text)

    def test_summary_skips_junk_and_prefers_descriptions(self):
        """Real bad summaries from the Rhode Island run are never chosen."""
        directions = ("From the north Rt6 to ri-94 South bear right on Howard hill road 438ft bear right "
                      "on s. Killingly rd. bear left onto walker rd 1.6 miles on left")
        check = "Mail a check to: Preserve Tiverton P.O. Box 196 Tiverton, RI 02878 and help us today."
        good = "Preserve Tiverton works to protect the rural character and open space of Tiverton, Rhode Island."
        self.assertEqual(choose_summary([(check, "meta"), (directions, "p"), (good, "p")], "DONT MALL TIVERTON"),
                         (good, "p"))
        self.assertEqual(choose_summary([("A Rhode Island nonprofit working for a better future", "meta")], "X"),
                         ("", ""))
        roster = ("President Gregory Smith (401) 486-5174 Vice President Tom Jones (401) 527-2802 "
                  "Secretary Sue Brown (401) 651-1407")
        self.assertEqual(choose_summary([(roster, "p")], "THORNTON BEAGLE CLUB"), ("", ""))

    def test_summary_is_trimmed_to_whole_sentences(self):
        text = ("Friends of Campbell Creek Science Center has become Friends of Campbell Tract. "
                "We are expanding to support users across all of Campbell Tract! Please bear with us. The Campbell")
        self.assertTrue(tidy_summary(text).endswith("Please bear with us."))
        long_text = "Sentence one is about our trail work in Milford. " * 12
        self.assertLessEqual(len(tidy_summary(long_text)), 320)


if __name__ == "__main__":
    unittest.main()
