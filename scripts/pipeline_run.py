"""Run one queued ``pipeline_runs`` request; called by .github/workflows/pipeline.yml.

    python -m scripts.pipeline_run <run id>

The row is claimed only while it is still ``queued`` (an admin may have
cancelled it), marked ``running`` with a link to the GitHub log, and finished as
``succeeded`` with the run's counts or ``failed`` with the error. Every run also
geocodes new addresses (``--use-census``; cached addresses are not resubmitted).
"""

from __future__ import annotations

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import main  # noqa: E402
from scripts import supabase_store as store  # noqa: E402
from scripts.load_environment import load_environment  # noqa: E402


def pipeline_arguments(run: dict) -> list[str]:
    """``main.py`` options for one run request."""
    if run["kind"] == "irs_refresh":
        return ["--rebuild", "--use-census", "--no-serve"]
    return [
        "--enrich-with-jev", "--enrichment-state", run["state"], "--enrichment-limit", str(run["org_limit"]),
        "--use-census", "--no-serve",
    ]


def update_run(run_id: int, fields: dict, only_if_status: str | None = None) -> list[dict]:
    """Change one run row; returns the updated rows (empty when the status didn't match)."""
    path = f"pipeline_runs?id=eq.{run_id}" + (f"&status=eq.{only_if_status}" if only_if_status else "")
    return json.loads(store._request(path, fields, "PATCH", "return=representation"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute(run_id: int) -> str:
    """Claim, run and record one request; returns its final status."""
    claimed = update_run(
        run_id, {"status": "running", "started_at": now(), "run_url": os.environ.get("RUN_URL")}, only_if_status="queued"
    )
    if not claimed:
        print(f"Run {run_id} is not queued (cancelled or already handled); nothing to do.", flush=True)
        return "skipped"
    run = claimed[0]
    print(f"Run {run_id}: {run['kind']} {run.get('state') or ''} limit {run.get('org_limit') or '-'}", flush=True)
    try:
        summary = main.run_pipeline(main.parse_args(pipeline_arguments(run)))
    except BaseException as error:  # includes the cancel/timeout interrupt from GitHub
        update_run(run_id, {"status": "failed", "finished_at": now(), "error": f"{type(error).__name__}: {error}"[:2000]})
        raise
    update_run(run_id, {"status": "succeeded", "finished_at": now(), "summary": summary})
    return "succeeded"


if __name__ == "__main__":
    load_environment(PROJECT_ROOT / ".env")
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        raise SystemExit("usage: python -m scripts.pipeline_run <run id>")
    execute(int(sys.argv[1]))
