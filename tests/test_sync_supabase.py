"""Tests for the Supabase sync helpers (no network)."""

import json
import unittest

from scripts.sync_supabase import batches, config_js, pipeline_rows


class SyncSupabaseTests(unittest.TestCase):
    def test_rows_are_properties_with_ids_only(self):
        payload = {"features": [{"properties": {"id": "a", "name": "A"}}, {"properties": {"name": "no id"}}, {"properties": {}}]}
        self.assertEqual(pipeline_rows(payload), [{"id": "a", "name": "A"}])

    def test_batches_cover_every_row_once(self):
        self.assertEqual([len(b) for b in batches(list(range(1201)), 500)], [500, 500, 201])

    def test_config_is_valid_javascript_assignment(self):
        line = config_js("https://x.supabase.co", "anon").splitlines()[-1]
        self.assertTrue(line.startswith("window.SUPABASE_CONFIG = "))
        self.assertEqual(json.loads(line.removeprefix("window.SUPABASE_CONFIG = ").rstrip(";")), {"url": "https://x.supabase.co", "anonKey": "anon"})


if __name__ == "__main__":
    unittest.main()
