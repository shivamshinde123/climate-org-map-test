"""Fetch and cache ProPublica Nonprofit Explorer records by IRS EIN.

Examples
--------
Fetch a small, stratified research sample (up to two organizations per NTEE):

    python scripts/fetch_propublica_nonprofits.py --per-ntee 2

Fetch every organization not already cached:

    python scripts/fetch_propublica_nonprofits.py --all

The script is intentionally incremental.  A valid ``raw/<EIN>.json`` response
is never fetched again unless ``--refresh`` is supplied.  Errors are recorded
in JSON Lines so a long run can be audited and safely resumed.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    # Direct execution (``python scripts/fetch_...py``) puts ``scripts`` on
    # sys.path, so the sibling import is available at top level.
    from propublica_common import (
        DEFAULT_DATA_DIR,
        DEFAULT_INPUT,
        PROPUBLICA_API_BASE,
        feature_ein,
        first_present,
        iter_geojson_features,
        normalize_ein,
    )
except ModuleNotFoundError:  # Package-style import used by tests and tooling.
    from scripts.propublica_common import (
        DEFAULT_DATA_DIR,
        DEFAULT_INPUT,
        PROPUBLICA_API_BASE,
        feature_ein,
        first_present,
        iter_geojson_features,
        normalize_ein,
    )


USER_AGENT = "ClimateOrgMapping/1.0 (research; ProPublica Nonprofit Explorer API)"


def utc_now() -> str:
    """Return an ISO timestamp suitable for manifests and reproducible audits."""

    return datetime.now(timezone.utc).isoformat()


def is_valid_cached_response(path: Path, ein: str) -> bool:
    """Check that a cache file is readable and represents the requested EIN."""

    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    organization = payload.get("organization") or {}
    cached = str(first_present(organization, "ein", "strein") or "")
    cached = "".join(character for character in cached if character.isdigit()).zfill(9)
    return cached == ein


def select_features(
    input_path: Path,
    *,
    fetch_all: bool,
    per_ntee: int,
    limit: int | None,
    seed: int,
    eins: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Select records deterministically, optionally stratified by IRS NTEE code.

    Stratification is useful for category research: a plain sample could be
    dominated by a common NTEE code and hide behavior in smaller groups.
    """

    features = [feature for feature in iter_geojson_features(input_path) if feature_ein(feature)]
    # An explicit EIN list is useful for reproducing a documented spot check.
    # Preserve the caller's order while silently ignoring EINs absent from the
    # map input; the final selected count makes omissions visible.
    requested_eins = [normalize_ein(value) for value in (eins or [])]
    requested_eins = [ein for ein in requested_eins if ein]
    if requested_eins:
        by_ein = {feature_ein(feature): feature for feature in features}
        return [by_ein[ein] for ein in requested_eins if ein in by_ein]

    rng = random.Random(seed)
    rng.shuffle(features)

    if fetch_all:
        selected = features
    else:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for feature in features:
            properties = feature.get("properties") or {}
            ntee = str(
                first_present(
                    properties,
                    "ntee_code",
                    "NTEE_CD",
                    "raw_ntee_code",
                    "source_ntee_code",
                    "ntee",
                )
                or "UNKNOWN"
            ).strip()
            if len(groups[ntee]) < per_ntee:
                groups[ntee].append(feature)
        selected = [feature for ntee in sorted(groups) for feature in groups[ntee]]

    return selected[:limit] if limit is not None else selected


def request_json(url: str, *, attempts: int = 5, timeout: float = 30.0) -> dict[str, Any]:
    """GET JSON with bounded exponential retry for transient server failures."""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # A missing organization is definitive.  Rate limits and server
            # errors are usually temporary and should be retried.
            if exc.code == 404 or (exc.code < 500 and exc.code != 429):
                raise
            if attempt == attempts - 1:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Retry loop ended unexpectedly")


def append_manifest(path: Path, event: dict[str, Any]) -> None:
    """Append one independently parseable audit event."""

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def fetch(args: argparse.Namespace) -> dict[str, int]:
    """Execute the incremental fetch and return counters for command output."""

    output_dir: Path = args.output_dir
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "fetch-manifest.jsonl"
    selected = select_features(
        args.input,
        fetch_all=args.all,
        per_ntee=args.per_ntee,
        limit=args.limit,
        seed=args.seed,
        eins=args.eins,
    )
    counters = {"selected": len(selected), "fetched": 0, "cached": 0, "failed": 0}

    for feature in selected:
        ein = feature_ein(feature)
        destination = raw_dir / f"{ein}.json"
        if not args.refresh and is_valid_cached_response(destination, ein):
            counters["cached"] += 1
            continue

        url = f"{PROPUBLICA_API_BASE}/organizations/{ein}.json"
        event: dict[str, Any] = {"timestamp": utc_now(), "ein": ein, "url": url}
        try:
            payload = request_json(url, attempts=args.attempts, timeout=args.timeout)
            # Write via a sibling temporary file so an interruption cannot leave
            # a partial JSON document that would masquerade as cached data.
            temporary = destination.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(destination)
            counters["fetched"] += 1
            event["status"] = "fetched"
        except Exception as exc:  # Log per-record failures and continue the batch.
            counters["failed"] += 1
            event.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
        append_manifest(manifest, event)
        if args.delay:
            time.sleep(args.delay)

    return counters


def build_parser() -> argparse.ArgumentParser:
    """Define a CLI that defaults to a safe, small research sample."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--per-ntee", type=int, default=2, help="Sample size per IRS NTEE code (default: 2).")
    parser.add_argument("--all", action="store_true", help="Fetch every input EIN rather than a stratified sample.")
    parser.add_argument("--limit", type=int, help="Optional hard cap after selection.")
    parser.add_argument("--seed", type=int, default=20261007)
    parser.add_argument(
        "--eins",
        nargs="+",
        help="Fetch specific project EINs (hyphenated or digits); overrides stratified selection.",
    )
    parser.add_argument("--delay", type=float, default=0.25, help="Polite delay between requests in seconds.")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--refresh", action="store_true", help="Replace valid cached responses.")
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    result = fetch(parsed)
    print(json.dumps(result, indent=2))
