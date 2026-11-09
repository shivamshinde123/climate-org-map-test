"""Survey verification is matched on EIN and only touches listed organizations."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.survey_verifications import apply_survey_verifications


class SurveyVerificationTests(unittest.TestCase):
    def test_marks_only_matching_ein(self):
        features = [
            {"properties": {"source_id": "871173877", "gcc_verification": "Not Verified", "status": None}},
            {"properties": {"source_id": "123456789", "gcc_verification": "Not Verified"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            path.write_text(json.dumps([{"ein": "871173877", "survey": "gb_survey", "evidence": "answered itself"}]))
            self.assertEqual(apply_survey_verifications(features, path), 1)
        self.assertEqual(features[0]["properties"]["gcc_verification"], "Verified")
        self.assertTrue(features[0]["properties"]["validated"])
        self.assertEqual(features[1]["properties"]["gcc_verification"], "Not Verified")

    def test_missing_file_changes_nothing(self):
        self.assertEqual(apply_survey_verifications([], Path("does-not-exist.json")), 0)


if __name__ == "__main__":
    unittest.main()
