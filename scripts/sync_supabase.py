"""Copy the pipeline's map dataset into the Supabase ``organizations`` table.

Run after ``main.py`` (or on its own) with the keys in ``.env``:

    python -m scripts.sync_supabase

It upserts every organization through the ``sync_pipeline_organizations``
database function, which skips rows the admin or a visitor changed, records the
admin emails, and writes the public URL and anon key to ``app/supabase-config.js``
for the map and the forms. The service role key stays in ``.env``.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

try:
    from .load_environment import load_environment
except ImportError:  # Allows direct execution from the scripts directory.
    from load_environment import load_environment  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "app" / "data" / "organizations.geojson"
CONFIG_JS = PROJECT_ROOT / "app" / "supabase-config.js"
BATCH_SIZE = 500


def pipeline_rows(payload: dict) -> list[dict]:
    """Return one properties object per organization, keyed by its ``id``."""
    return [feature["properties"] for feature in payload.get("features", []) if feature.get("properties", {}).get("id")]


def batches(rows: list, size: int = BATCH_SIZE):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def config_js(url: str, anon_key: str) -> str:
    return (
        "// Public Supabase settings, written by scripts/sync_supabase.py.\n"
        "// The anon key is public by design; database access rules protect the data.\n"
        f"window.SUPABASE_CONFIG = {json.dumps({'url': url, 'anonKey': anon_key})};\n"
    )


def _post(url: str, key: str, path: str, body, prefer: str = "return=minimal") -> bytes:
    request = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": prefer},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args()
    load_environment(PROJECT_ROOT / ".env")
    url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    admins = [email.strip() for email in os.environ.get("ADMIN_EMAILS", "").split(",") if email.strip()]
    if admins:
        _post(url, service_key, "admins", [{"email": email} for email in admins], "resolution=ignore-duplicates,return=minimal")

    rows = pipeline_rows(json.loads(args.dataset.read_text(encoding="utf-8")))
    written = 0
    for batch in batches(rows):
        written += int(_post(url, service_key, "rpc/sync_pipeline_organizations", {"rows": batch}, "return=representation"))
        print(f"\r      Synced {min(written, len(rows)):,} changed of {len(rows):,}", end="", flush=True)
    print(f"\n      Organizations sent: {len(rows):,}; inserted or changed: {written:,}; admins: {len(admins)}")

    CONFIG_JS.write_text(config_js(url, os.environ["SUPABASE_ANON_KEY"]), encoding="utf-8")
    print(f"      Wrote {CONFIG_JS.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
