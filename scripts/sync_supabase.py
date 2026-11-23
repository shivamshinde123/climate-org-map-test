"""Apply the Supabase settings from ``.env``.

Run whenever ``ADMIN_EMAILS`` or the Supabase project changes:

    python -m scripts.sync_supabase

It makes the ``admins`` table match ``ADMIN_EMAILS`` exactly (adding and removing emails;
an empty ``ADMIN_EMAILS`` leaves it unchanged), and writes the public URL and anon key to ``app/supabase-config.js``
for the map and the forms. The service role key stays in ``.env``. (The
pipeline writes organizations to Supabase itself; see ``supabase_store.py``.)
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from .load_environment import load_environment
except ImportError:  # Allows direct execution from the scripts directory.
    from load_environment import load_environment  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_JS = PROJECT_ROOT / "app" / "supabase-config.js"


def config_js(url: str, anon_key: str) -> str:
    return (
        "// Public Supabase settings, written by scripts/sync_supabase.py.\n"
        "// The anon key is public by design; database access rules protect the data.\n"
        f"window.SUPABASE_CONFIG = {json.dumps({'url': url, 'anonKey': anon_key})};\n"
    )


def admin_emails(value: str) -> list[str]:
    """ADMIN_EMAILS ("a@x.org, B@y.org") -> sorted, lower-cased, without duplicates."""
    return sorted({email.strip().lower() for email in value.split(",") if email.strip()})


def removal_filter(keep: list[str]) -> str:
    """PostgREST filter for admin rows whose email is not in `keep`."""
    quoted = ",".join('"' + email.replace("\\", "\\\\").replace('"', '\\"') + '"' for email in keep)
    return "email=" + urllib.parse.quote(f"not.in.({quoted})", safe="")


def _post(url: str, key: str, path: str, body, prefer: str = "return=minimal", method: str = "POST") -> bytes:
    request = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": prefer},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    load_environment(PROJECT_ROOT / ".env")
    url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    admins = admin_emails(os.environ.get("ADMIN_EMAILS", ""))
    if admins:
        # The table matches ADMIN_EMAILS exactly: add new emails, then remove the rest.
        _post(url, service_key, "admins", [{"email": email} for email in admins], "resolution=ignore-duplicates,return=minimal")
        removed = json.loads(_post(url, service_key, f"admins?{removal_filter(admins)}", None, "return=representation", "DELETE"))
        if removed:
            print(f"      Removed admins: {', '.join(row['email'] for row in removed)}")
    else:
        # An empty setting is more likely a mistake than a wish to lock everyone out.
        print("      ADMIN_EMAILS is empty; admin list left unchanged.")

    print(f"      Admins: {len(admins)}")

    CONFIG_JS.write_text(config_js(url, os.environ["SUPABASE_ANON_KEY"]), encoding="utf-8")
    print(f"      Wrote {CONFIG_JS.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
