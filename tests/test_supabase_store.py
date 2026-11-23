"""NUL characters are dropped before a write; everything else survives."""

import json
import unittest

from scripts.supabase_store import _NUL, feature


class SupabaseStoreTests(unittest.TestCase):
    def test_nul_is_removed_but_escaped_backslash_text_is_kept(self):
        text = json.dumps({"a": "x\x00y", "b": "path\\u0000", "c": "\\\x00"}, ensure_ascii=False)
        cleaned = json.loads(_NUL.sub(r"\1", text))
        self.assertEqual(cleaned, {"a": "xy", "b": "path\\u0000", "c": "\\"})

    def test_feature_point_needs_numeric_coordinates(self):
        self.assertEqual(feature({"latitude": 42.0, "longitude": -71.0})["geometry"]["coordinates"], [-71.0, 42.0])
        self.assertIsNone(feature({"latitude": "", "longitude": ""})["geometry"])


if __name__ == "__main__":
    unittest.main()
