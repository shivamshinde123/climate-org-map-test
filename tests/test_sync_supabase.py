"""Tests for the Supabase sync helpers (no network)."""

import json
import unittest

from scripts.sync_supabase import admin_emails, config_js


class SyncSupabaseTests(unittest.TestCase):
    def test_admin_emails_are_normalized(self):
        self.assertEqual(admin_emails(" B@y.org, a@x.org,,b@y.org "), ["a@x.org", "b@y.org"])
        self.assertEqual(admin_emails(""), [])

    def test_config_is_valid_javascript_assignment(self):
        line = config_js("https://x.supabase.co", "anon").splitlines()[-1]
        self.assertTrue(line.startswith("window.SUPABASE_CONFIG = "))
        self.assertEqual(json.loads(line.removeprefix("window.SUPABASE_CONFIG = ").rstrip(";")), {"url": "https://x.supabase.co", "anonKey": "anon"})


if __name__ == "__main__":
    unittest.main()
