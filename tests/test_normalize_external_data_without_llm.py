"""Tests for the deterministic adapter used by future external data sources."""

import unittest

from scripts.normalize_external_data_without_llm import canonical_category, normalize_record


class NormalizeExternalDataTests(unittest.TestCase):
    """Protect precedence rules and the closed category vocabulary."""

    def test_explicit_recognized_values_take_priority(self):
        """Known aliases and synonyms outrank fallback inference."""
        record = {
            "org_name": "Metro Climate Collaborative",
            "street": "1 Main St",
            "town": "Worcester",
            "state_code": "ma",
            "zip": "01609",
            "type": "alliance",
            "audience": "public",
            "resilience": "emissions reduction",
            "activity": "policy",
            "climate_focus": "transit",
            "scope": "county",
            "verified": "yes",
        }
        output = normalize_record(record, "Example Source")
        self.assertEqual(output["organization_type"], "Coalition")
        self.assertEqual(output["audience_focus"], "Residents")
        self.assertEqual(output["adaptation_vs_mitigation"], "Mitigation")
        self.assertEqual(output["advocacy_vs_action"], "Advocacy")
        self.assertEqual(output["climate_categories"], "Transportation")
        self.assertEqual(output["reach"], "Regional")
        self.assertEqual(output["status"], "Verified")
        self.assertTrue(output["validated"])
        self.assertEqual(output["state"], "MA")

    def test_unknown_values_use_deterministic_inference(self):
        """Missing categories fall back to reproducible keyword rules."""
        record = {
            "name": "Neighborhood Solar Action Network",
            "address": "2 Main St",
            "city": "Boston",
            "state": "MA",
            "postal_code": "02108",
        }
        output = normalize_record(record, "Example Source")
        self.assertEqual(output["organization_type"], "Coalition")
        self.assertEqual(output["climate_categories"], "Energy Efficiency")
        self.assertEqual(output["reach"], "Town / City")
        self.assertEqual(output["status"], "Not Verified")

    def test_canonical_category_never_emits_uncontrolled_value(self):
        """Novel source labels resolve to safe schema defaults."""
        self.assertEqual(canonical_category("organization_type", "something novel"), "Unknown")
        self.assertEqual(canonical_category("status", "pending"), "Not Verified")

    def test_source_category_label_uses_shared_crosswalk(self):
        """Equivalent external labels map through the same taxonomy as IRS."""
        output = normalize_record(
            {
                "name": "Community Materials Exchange",
                "category": "Recycling",
            },
            "Community Directory",
        )

        self.assertEqual(output["ntee_code"], "C27")
        self.assertEqual(output["climate_categories"], "Waste Reduction")
        self.assertEqual(output["action_category"], "Other")
        self.assertEqual(output["advocacy_vs_action"], "Action")
        self.assertEqual(output["adaptation_vs_mitigation"], "Unknown")
        self.assertEqual(
            output["source_category_mapping_basis"],
            "source category label -> NTEE C27",
        )
        self.assertEqual(output["source_category_mapping_version"], "2.1.0")


if __name__ == "__main__":
    unittest.main()
