"""Tests for the API audit log and the logged Brave discovery path."""

import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from scripts import api_log, website_discovery


class FakeResponse(io.BytesIO):
    """Minimal stand-in for an ``urlopen`` response."""

    status = 200
    headers = {"x-request-id": "req-1", "set-cookie": "secret"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class ApiLogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.log = Path(self.directory.name) / "api.jsonl"
        for target, attribute, value in (
            (api_log, "LOG_PATH", self.log),
            (website_discovery, "BRAVE_CACHE_PATH", Path(self.directory.name) / "brave.jsonl"),
            (website_discovery, "_brave_cache", None),
        ):
            patcher = mock.patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.directory.cleanup)

    def entries(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_request_is_logged_in_full_without_secrets(self):
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps({"model": "m"}).encode(),
            headers={"Authorization": "Bearer sk-secret", "Content-Type": "application/json"},
            method="POST",
        )
        api_log.record_context.set({"org_id": "org_1"})
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b'{"usage": {"cost": 0.01}}')):
            api_log.send(request, "openrouter", "jev_classification", timeout=5)

        entry = self.entries()[0]
        self.assertEqual(entry["org_id"], "org_1")
        self.assertEqual(entry["request_body"], {"model": "m"})
        self.assertEqual(entry["response_body"]["usage"]["cost"], 0.01)
        self.assertEqual(entry["status"], 200)
        self.assertNotIn("sk-secret", self.log.read_text(encoding="utf-8"))
        self.assertNotIn("set-cookie", entry["response_headers"])

    def test_http_error_is_logged_and_body_stays_readable(self):
        error = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b'{"error": "bad key"}'))
        request = urllib.request.Request("https://api.search.brave.com/x")
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                api_log.send(request, "brave", "website_discovery", timeout=5)
        self.assertIn(b"bad key", raised.exception.read())
        self.assertEqual(self.entries()[0]["status"], 401)

    def test_brave_uses_homepage_description_and_rejects_bad_keys(self):
        org = {"name": "Green Beverly Coalition", "city": "Beverly", "state": "MA"}
        results = {"web": {"results": [{
            "url": "https://greenbeverly.org/",
            "title": "Green Beverly Coalition",
            "description": "The <strong>Green Beverly</strong> Coalition in Beverly, MA &amp; more",
        }]}}
        with mock.patch.object(api_log, "send", return_value=json.dumps(results).encode()), \
                mock.patch.object(website_discovery, "page_profile", return_value={
                    "description": "Green Beverly Coalition brings Beverly residents together to cut emissions and restore parks.", "paragraphs": [], "excerpt": "Body text"}):
            found = website_discovery.brave_discover(org, "key")
        self.assertEqual(found["summary"], "Green Beverly Coalition brings Beverly residents together to cut emissions and restore parks.")
        self.assertIn("The Green Beverly Coalition in Beverly, MA & more", found["evidence"])
        self.assertEqual(self.entries()[0]["kind"], "brave_accepted")

        # The same search again is served from the cache: no second API call.
        with mock.patch.object(api_log, "send") as send, \
                mock.patch.object(website_discovery, "page_profile", return_value={
                    "description": "Green Beverly Coalition brings Beverly residents together to cut emissions and restore parks.", "paragraphs": [], "excerpt": ""}):
            website_discovery.brave_discover(org, "key")
        send.assert_not_called()

        rejected = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        with mock.patch.object(api_log, "send", side_effect=rejected):
            with self.assertRaises(website_discovery.BraveKeyError):
                website_discovery.brave_discover({**org, "name": "Other Group"}, "bad-key")

    def test_brave_prefers_own_domain_over_pages_about_the_org(self):
        org = {"name": "WOONASQUATUCKET RIVER WATERSHED COUNCIL", "city": "PROVIDENCE", "state": "RI"}
        title = "Woonasquatucket River Watershed Council, Providence, Rhode Island"
        results = {"web": {"results": [
            {"url": "https://volunteer.uwri.org/agency/detail/?agency_id=88668", "title": title, "description": title},
            {"url": "https://ecori.org/woonasquatucket-river-watershed-council-cleanup-2025/", "title": title, "description": title},
            {"url": "https://wrwc.org/about/", "title": "About us", "description": "Woonasquatucket River Watershed Council"},
        ]}}
        with mock.patch.object(api_log, "send", return_value=json.dumps(results).encode()), \
                mock.patch.object(website_discovery, "page_profile", return_value={
                    "description": "The council restores the Woonasquatucket River and its parks for Providence neighborhoods.", "paragraphs": [], "excerpt": ""}):
            found = website_discovery.brave_discover(org, "key")
        self.assertEqual(found["website_url"], "https://wrwc.org/")

    def test_facebook_page_comes_from_cached_results_only(self):
        org = {"name": "MIDDLE DAM POND CONSERVATION ASSOCIATION", "city": "COVENTRY", "state": "RI"}
        self.assertEqual(website_discovery.facebook_page(org), "")  # nothing cached: no API call, no page
        website_discovery._store_brave_results(website_discovery.brave_query(org), [
            {"url": "https://www.facebook.com/events/123/"},
            {"url": "https://www.facebook.com/SomeOtherGroup/"},
            {"url": "https://m.facebook.com/MiddleDamPond/posts/9"},
        ])
        self.assertEqual(website_discovery.facebook_page(org), "https://www.facebook.com/MiddleDamPond/")
        other = {**org, "city": "WARWICK"}
        website_discovery._store_brave_results(website_discovery.brave_query(other), [
            {"url": "https://www.facebook.com/groups/OurNK/posts/3871916723037558/"},
            {"url": "https://www.facebook.com/p/Middle-Dam-Pond-Conservation-Association-100091443049715/"},
        ])
        self.assertEqual(website_discovery.facebook_page(other),
                         "https://www.facebook.com/p/Middle-Dam-Pond-Conservation-Association-100091443049715/")


if __name__ == "__main__":
    unittest.main()
