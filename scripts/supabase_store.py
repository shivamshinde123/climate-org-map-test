"""Supabase, the pipeline's only data store.

Every stage reads organizations from and writes them back to the
``organizations`` table, paid API answers go to ``pipeline_cache``, the request
audit to ``api_log``, and survey evidence comes from ``survey_verifications``.
All calls use the service role key from ``.env`` (``SUPABASE_URL``,
``SUPABASE_SERVICE_ROLE_KEY``), so they bypass the browser's access rules.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

PAGE_SIZE = 1000  # PostgREST's default maximum rows per response
BATCH_SIZE = 500
# A JSON-escaped NUL (an odd number of backslashes, then u0000); an escaped
# backslash followed by the text "u0000" is left alone.
_NUL = re.compile(r"(?<!\\)((?:\\\\)*)\\u0000")

# Serialized properties as loaded, so a save sends only what changed.
_loaded: dict[str, str] = {}


def _request(path: str, body=None, method: str = "GET", prefer: str = "return=minimal") -> bytes:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    # Postgres text cannot hold NUL; scraped pages sometimes contain it.
    data = None if body is None else _NUL.sub(r"\1", json.dumps(body, ensure_ascii=False, default=str)).encode()
    request = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        data=data,
        method=method,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": prefer},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _select_all(path: str) -> list[dict]:
    """Every row of a select, a page at a time (``path`` must include an ``order``)."""
    rows, offset = [], 0
    while True:
        page = json.loads(_request(f"{path}&limit={PAGE_SIZE}&offset={offset}"))
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def feature(properties: dict) -> dict:
    """A GeoJSON feature; the point comes from the stored latitude/longitude."""
    latitude, longitude = properties.get("latitude"), properties.get("longitude")
    located = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (latitude, longitude))
    geometry = {"type": "Point", "coordinates": [longitude, latitude]} if located else None
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _serialized(properties: dict) -> str:
    return json.dumps(properties, sort_keys=True, ensure_ascii=False, default=str)


def load_payload() -> dict:
    """Every approved organization as a FeatureCollection (pending, rejected and removed are left out)."""
    rows = _select_all("organizations?select=id,properties&review_status=eq.approved&order=id")
    _loaded.clear()
    _loaded.update((row["id"], _serialized(row["properties"])) for row in rows)
    return {"type": "FeatureCollection", "features": [feature(row["properties"]) for row in rows]}


def save_payload(payload: dict) -> int:
    """Write new and changed organizations; return how many rows the database changed.

    Rows the admin or a visitor changed keep their values (see the
    ``sync_pipeline_organizations`` database function).
    """
    changed = [
        properties
        for properties in (f.get("properties", {}) for f in payload.get("features", []))
        if properties.get("id") and _loaded.get(properties["id"]) != _serialized(properties)
    ]
    written = 0
    for start in range(0, len(changed), BATCH_SIZE):
        batch = changed[start : start + BATCH_SIZE]
        written += int(_request("rpc/sync_pipeline_organizations", {"rows": batch}, "POST", "return=representation"))
        _loaded.update((p["id"], _serialized(p)) for p in batch)
    return written


def load_cache(kind: str) -> dict[str, dict]:
    """Cached API answers of one kind (``brave``, ``discovery``, ``jev``, ...) by key."""
    rows = _select_all(f"pipeline_cache?select=key,result&kind=eq.{urllib.parse.quote(kind)}&order=key")
    return {row["key"]: row["result"] for row in rows}


def append_cache(kind: str, key: str, result) -> None:
    """Store one API answer immediately so completed work survives interruption."""
    _request(
        "pipeline_cache?on_conflict=kind,key",
        {"kind": kind, "key": key, "result": result},
        "POST",
        "resolution=merge-duplicates,return=minimal",
    )


def save_cache(kind: str, results: dict) -> None:
    """Store many answers of one kind at once (``key -> result``)."""
    items = [{"kind": kind, "key": key, "result": result} for key, result in results.items()]
    for start in range(0, len(items), BATCH_SIZE):
        _request(
            "pipeline_cache?on_conflict=kind,key",
            items[start : start + BATCH_SIZE],
            "POST",
            "resolution=merge-duplicates,return=minimal",
        )


def write_log(entry: dict) -> None:
    _request("api_log", {"entry": entry}, "POST")


def survey_verifications() -> dict[str, dict]:
    """Survey evidence by EIN."""
    return {row["ein"]: row["record"] for row in _select_all("survey_verifications?select=ein,record&order=ein")}
