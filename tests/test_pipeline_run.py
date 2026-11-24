"""A run request is claimed only while queued and always ends with its outcome recorded."""

import json
import unittest
from unittest import mock

from scripts import pipeline_run


class PipelineRunTests(unittest.TestCase):
    def setUp(self):
        self.row = {"id": 7, "kind": "extract", "state": "RI", "org_limit": 25, "status": "queued"}
        self.calls = []

        def fake_request(path, body=None, method="GET", prefer=""):
            self.calls.append((path, body))
            if "status=eq.queued" in path and self.row["status"] != "queued":
                return "[]"
            self.row.update(body)
            return json.dumps([self.row])

        patcher = mock.patch.object(pipeline_run.store, "_request", fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_success_records_running_then_summary(self):
        with mock.patch.object(pipeline_run.main, "run_pipeline", return_value={"processed": 25}) as run:
            self.assertEqual(pipeline_run.execute(7), "succeeded")
        args = run.call_args.args[0]
        self.assertEqual((args.enrichment_state, args.enrichment_limit), ("RI", 25))
        self.assertTrue(args.enrich_with_jev and args.use_census and args.no_serve)
        self.assertEqual(self.calls[0][1]["status"], "running")
        self.assertEqual(self.row["status"], "succeeded")
        self.assertEqual(self.row["summary"], {"processed": 25})

    def test_failure_is_recorded_and_reraised(self):
        with mock.patch.object(pipeline_run.main, "run_pipeline", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                pipeline_run.execute(7)
        self.assertEqual(self.row["status"], "failed")
        self.assertIn("KeyboardInterrupt", self.row["error"])

    def test_cancelled_request_is_not_run(self):
        self.row["status"] = "cancelled"
        with mock.patch.object(pipeline_run.main, "run_pipeline") as run:
            self.assertEqual(pipeline_run.execute(7), "skipped")
        run.assert_not_called()

    def test_irs_refresh_rebuilds_without_paid_extraction(self):
        args = pipeline_run.main.parse_args(pipeline_run.pipeline_arguments({"kind": "irs_refresh"}))
        self.assertTrue(args.rebuild and args.use_census)
        self.assertFalse(args.enrich_with_jev)


if __name__ == "__main__":
    unittest.main()
