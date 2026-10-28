"""Contract tests for website discovery and single-request Jev enrichment."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.enrich_organizations_with_jev import (
    CLASSIFICATION_FIELDS,
    apply_enrichment,
    enrich_geojson,
    jev_request_payload,
    website_discovery_payload,
)
from scripts.normalize_external_data_without_llm import CATEGORY_OPTIONS


class EnrichOrganizationsWithJevTests(unittest.TestCase):
    """Verify evidence separation, schema completeness, and incremental reuse."""

    def setUp(self):
        """Create one reusable organization, discovery result, and Jev decision."""
        self.properties = {
            "id": "org_test",
            "name": "New Hampshire Climate Action Network",
            "address": "17 High St",
            "city": "Plymouth",
            "state": "NH",
            "postal_code": "03264",
            "source_id": "123456789",
            "irs_category": "C01 - Alliance/Advocacy Organizations",
        }
        self.discovery = {
            "status": "found",
            "website_url": "https://example.org/",
            "summary": "The organization advances climate action in New Hampshire.",
            "evidence": "The official site describes statewide climate advocacy programs.",
            "source_urls": ["https://example.org/about"],
            "confidence": "high",
            "rationale": "Name and location match the IRS record.",
        }
        # Supply a valid choice for every controlled field; probabilities mimic
        # the Decisions API shape while remaining deterministic in the test.
        choices = {
            "organization_type": "Nonprofit / Grassroots",
            "audience_focus": "Residents",
            "adaptation_vs_mitigation": "Both",
            "advocacy_vs_action": "Advocacy",
            "action_category": "Advocacy/Policy",
            "climate_categories": "Environmental",
            "reach": "State / National",
            "status": "Not Verified",
        }
        self.jev_response = {
            "model": "typesafe/jev-1.13-20260917",
            "provider": "TypeSafe",
            "id": "gen-dec-test",
            "answers": {
                field: {
                    "type": "choice",
                    "choice": choice,
                    "probabilities": {option: 1.0 if option == choice else 0.0 for option in CATEGORY_OPTIONS[field]},
                    "confidence": 1.0,
                }
                for field, choice in choices.items()
            },
        }

    def test_discovery_uses_openai_web_search_and_structured_output(self):
        """Discovery requests web search and a strict machine-readable response."""
        payload = website_discovery_payload(self.properties, "search-model")
        self.assertEqual(payload["tools"], [{"type": "web_search", "search_context_size": "medium"}])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertIn("New Hampshire Climate Action Network", payload["input"])

    def test_jev_receives_all_schema_filters_in_one_request(self):
        """All eight category decisions share one evidence state and API call."""
        payload = jev_request_payload(self.properties, self.discovery, "typesafe/jev-1.13")
        self.assertEqual(payload["model"], "typesafe/jev-1.13")
        self.assertEqual(set(payload["questions"]), set(CLASSIFICATION_FIELDS))
        self.assertEqual(len(payload["questions"]), 8)
        self.assertTrue(all(question["type"] == "choice" for question in payload["questions"].values()))

    def test_apply_enrichment_updates_popup_and_filter_fields(self):
        """Validated results populate both tooltip and canonical filter fields."""
        apply_enrichment(self.properties, self.discovery, self.jev_response, "typesafe/jev-1.13")
        self.assertEqual(self.properties["website_url"], "https://example.org/")
        self.assertEqual(self.properties["summary"], self.discovery["summary"])
        self.assertEqual(self.properties["gcc_activity"], "Advocacy")
        self.assertEqual(self.properties["gcc_reach"], "State / National")
        self.assertFalse(self.properties["validated"])
        self.assertEqual(self.properties["jev_request_id"], "gen-dec-test")

    def test_pipeline_caches_discovery_and_jev_results(self):
        """A second run performs no paid calls for an already complete record."""
        discovery_calls = []
        jev_calls = []

        def discover(payload, _key, _endpoint):
            """Record and return the deterministic fake discovery response."""
            discovery_calls.append(payload)
            return self.discovery

        def decide(payload, _key, _endpoint):
            """Record and return the deterministic fake Jev response."""
            jev_calls.append(payload)
            return self.jev_response

        collection = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": None, "properties": self.properties}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.geojson"
            output = root / "output.geojson"
            discovery_cache = root / "discovery.jsonl"
            jev_cache = root / "jev.jsonl"
            source.write_text(json.dumps(collection), encoding="utf-8")
            no_contacts = lambda *_: {"email": "", "phone": "", "contact_page_url": ""}
            stats = enrich_geojson(
                source, output, "openai-key", "openrouter-key",
                discovery_cache, jev_cache,
                discovery_caller=discover, jev_caller=decide,
                contact_caller=no_contacts,
            )
            self.assertEqual(stats["classified"], 1)
            stats = enrich_geojson(
                output, output, "openai-key", "openrouter-key",
                discovery_cache, jev_cache,
                discovery_caller=discover, jev_caller=decide,
                contact_caller=no_contacts,
            )
            self.assertEqual(stats["classified"], 0)
            self.assertEqual(stats["skipped_existing"], 1)
            self.assertEqual(stats["processed"], 0)
            result = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(len(discovery_calls), 1)
        self.assertEqual(len(jev_calls), 1)
        self.assertEqual(result["features"][0]["properties"]["website_url"], "https://example.org/")


if __name__ == "__main__":
    unittest.main()
