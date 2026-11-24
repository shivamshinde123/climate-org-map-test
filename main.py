#!/usr/bin/env python3
"""Run the complete Climate Org Mapping development pipeline.

This is the repository's primary entry point.  It coordinates four concerns that
are deliberately kept in separate modules: IRS normalization, coordinate
assignment, optional paid enrichment, and static-file serving.  Supabase is the
only data store: every run loads the organizations from the database and saves
the new and changed ones back.  Normal runs are incremental: existing records
and completed coordinates are reused, while ``--rebuild`` explicitly opts into
regenerating the IRS base.

No API key is sent anywhere merely by starting the application.  Census calls
require ``--use-census`` and paid OpenRouter calls require
``--enrich-with-jev``.
"""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts import supabase_store as store
from scripts.build_irs_dataset import build_dataset, download_irs_files
from scripts.geocode_organizations import DEFAULT_ENDPOINT, geocode_dataset
from scripts.load_environment import load_environment
from scripts.enrich_organizations_with_jev import (
    DEFAULT_JEV_MODEL,
    DEFAULT_SEARCH_MODEL,
    OPENROUTER_CHAT_ENDPOINT,
    OPENROUTER_DECISIONS_ENDPOINT,
    enrich_payload,
)


# Resolve defaults from this file rather than the caller's working directory.
# This makes ``python main.py`` behave consistently from terminals, IDEs, and
# scheduled jobs.
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "Data"
DEFAULT_CODES_PATH = (
    PROJECT_ROOT
    / "Docs"
    / "Research and Requirements"
    / "NTEE_Codes_to_Consider.txt"
)
DEFAULT_APP_DIR = PROJECT_ROOT / "app"

# These fields are restored after a forced IRS rebuild when the preceding
# dataset says that Jev completed classification.  The overlay prevents a
# reproducible base-data refresh from destroying paid enrichment.
JEV_SCHEMA_FIELDS = {
    "organization_type", "audience_focus", "adaptation_vs_mitigation",
    "advocacy_vs_action", "action_category", "climate_categories", "reach",
    "status", "validated", "gcc_organization_type", "gcc_audience_focus",
    "gcc_resilience", "gcc_activity", "gcc_action_category",
    "gcc_climate_category", "gcc_reach", "gcc_verification",
}


def load_enrichment_overlay(payload: dict) -> dict[str, dict]:
    """Read reusable enrichment keyed by stable organization ID.

    Empty placeholder fields are intentionally excluded.  Website metadata is
    reusable independently, but GCC schema values are preserved only when the
    record proves that Jev classification completed successfully.
    """
    overlay = {}
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        saved = {
            key: value
            for key, value in properties.items()
            if value not in (None, "", [], {})
            and (
                key in {"website_url", "summary"}
                or key.startswith("website_")
                or key.startswith("jev_")
            )
        }
        if properties.get("jev_classification_status") == "classified":
            saved.update({key: properties.get(key) for key in JEV_SCHEMA_FIELDS})
        if saved:
            overlay[str(properties.get("id", ""))] = saved
    return overlay


def restore_enrichment(payload: dict, overlay: dict[str, dict]) -> int:
    """Merge a previously captured enrichment overlay into the rebuilt records.

    Returns the number of organizations restored.  Unknown IDs are ignored so
    records removed from the current IRS selection cannot reappear by accident.
    """
    restored = 0
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        saved = overlay.get(str(properties.get("id", "")))
        if saved:
            properties.update(saved)
            restored += 1
    return restored


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Define and validate the public command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--codes", type=Path, default=DEFAULT_CODES_PATH)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild existing normalized data instead of reusing the current output",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional organization limit for quick local testing",
    )
    parser.add_argument(
        "--use-census",
        action="store_true",
        help=(
            "Submit uncached public IRS address fields to the U.S. Census Geocoder; "
            "otherwise only cached matches and ZIP/city fallbacks are used"
        ),
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=argparse.SUPPRESS)
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument(
        "--enrich-with-jev",
        action="store_true",
        help="Discover websites with web search, then classify all schema fields with Jev through OpenRouter",
    )
    parser.add_argument(
        "--enrichment-limit",
        type=int,
        help="Limit paid website-search and Jev enrichment calls for pilot runs",
    )
    parser.add_argument(
        "--enrichment-state",
        help="Only enrich organizations in this two-letter state, e.g. MA",
    )
    parser.add_argument(
        "--contact-fallback",
        action="store_true",
        help="Pay for an OpenRouter contact lookup (about 2 cents) when a site blocks the crawler; off by default",
    )
    parser.add_argument("--search-model", default=os.environ.get("SEARCH_MODEL", DEFAULT_SEARCH_MODEL))
    parser.add_argument("--jev-model", default=os.environ.get("JEV_MODEL", DEFAULT_JEV_MODEL))
    parser.add_argument("--search-endpoint", default=os.environ.get("SEARCH_BASE_URL", OPENROUTER_CHAT_ENDPOINT), help=argparse.SUPPRESS)
    parser.add_argument("--jev-endpoint", default=os.environ.get("JEV_BASE_URL", OPENROUTER_DECISIONS_ENDPOINT), help=argparse.SUPPRESS)
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Run the pipeline without starting the local map server",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.enrichment_limit is not None and args.enrichment_limit < 1:
        parser.error("--enrichment-limit must be at least 1")
    if not 1 <= args.batch_size <= 10_000:
        parser.error("--batch-size must be between 1 and 10000")
    if not 1 <= args.port <= 65_535:
        parser.error("--port must be between 1 and 65535")
    return args


def validate_map_dataset(payload: dict) -> tuple[int, int, int]:
    """Validate map-critical GeoJSON invariants.

    The browser expects a non-empty FeatureCollection.  Null geometries are
    tolerated while inspecting individual records, but a published map must
    contain at least one valid Point.  The returned tuple is
    ``(record_count, point_count, approximate_point_count)``.
    """
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("The dataset does not contain any organization features")

    points = 0
    fallbacks = 0
    for feature in features:
        geometry = feature.get("geometry")
        if geometry is None:
            continue
        coordinates = geometry.get("coordinates", [])
        if geometry.get("type") != "Point" or len(coordinates) != 2:
            raise ValueError("Every non-null organization geometry must be a GeoJSON Point")
        longitude, latitude = coordinates
        if not (-180 <= float(longitude) <= 180 and -90 <= float(latitude) <= 90):
            raise ValueError(f"Invalid coordinates: {coordinates}")
        points += 1
        if feature.get("properties", {}).get("location_precision") in {"zip_level_fallback", "city_level_fallback"}:
            fallbacks += 1

    if points == 0:
        raise ValueError("The generated dataset contains no map-ready coordinates")
    return len(features), points, fallbacks


def dataset_has_complete_coordinates(payload: dict) -> bool:
    """Return whether every feature already has a final coordinate outcome.

    This inexpensive check is what lets ordinary runs skip the geocoder.  An
    explicit ``--use-census`` still re-enters geocoding so fallbacks can be
    upgraded to address-range matches. ``unavailable`` is final: neither a ZIP
    nor a city centroid matched, so the record has no point.
    """
    features = payload.get("features", [])

    def resolved(feature: dict) -> bool:
        precision = feature.get("properties", {}).get("location_precision")
        if precision == "unavailable":
            return True
        return (feature.get("geometry") or {}).get("type") == "Point" and precision in {
            "census_address_range", "zip_level_fallback", "city_level_fallback",
        }

    return bool(features) and all(resolved(feature) for feature in features)


def run_pipeline(args: argparse.Namespace) -> dict:
    """Execute enabled stages in dependency order, print progress, and return summary counts."""
    phase_count = 4 if args.enrich_with_jev else 3
    payload = store.load_payload()
    # An empty database must be built; existing records are authoritative
    # unless the operator explicitly requests a source refresh.
    should_build = args.rebuild or not payload["features"]
    if should_build:
        enrichment_overlay = load_enrichment_overlay(payload)
        print(f"[1/{phase_count}] Building normalized IRS dataset...", flush=True)
        changed = download_irs_files(args.input_dir / "IRS EO BMF")
        print(f"      IRS files downloaded (new or updated): {changed:,}")
        payload, stats = build_dataset(args.input_dir, args.codes, args.limit)
        print(f"      Scanned {stats.source_rows:,} IRS rows")
        print(f"      Selected {stats.emitted:,} organizations")
    else:
        print(f"[1/{phase_count}] Loaded {len(payload['features']):,} organizations from Supabase", flush=True)

    mode = "Census geocoding with ZIP/city fallback" if args.use_census else "cached coordinates and ZIP/city fallback"
    # Fallback-only coordinates are complete for map rendering.  Census mode is
    # nevertheless allowed to revisit them because it is an explicit upgrade.
    should_geocode = args.use_census or not dataset_has_complete_coordinates(payload)
    if should_geocode:
        print(f"[2/{phase_count}] Applying {mode}...", flush=True)
        submitted, matched, unmatched, fallbacks = geocode_dataset(
            payload,
            args.endpoint,
            args.batch_size,
            args.limit,
            fallback_only=not args.use_census,
        )
        print(f"      New addresses submitted: {submitted:,}")
        print(f"      Census coordinates applied: {matched:,}")
        print(f"      Cached non-matches: {unmatched:,}")
        print(f"      ZIP/city fallbacks applied: {fallbacks:,}")
    else:
        print(f"[2/{phase_count}] Reusing existing coordinates", flush=True)
    if should_build:
        restored = restore_enrichment(payload, enrichment_overlay)
        if restored:
            print(f"      Preserved existing enrichment: {restored:,} organizations")

    enrichment_stats: dict = {}
    try:
        if args.enrich_with_jev:
            print("[3/4] Discovering websites and classifying with Jev through OpenRouter...", flush=True)
            stats = enrich_payload(
                payload,
                os.environ["OPENROUTER_API_KEY"],
                args.search_model,
                args.jev_model,
                args.search_endpoint,
                args.jev_endpoint,
                args.enrichment_limit if args.enrichment_limit is not None else args.limit,
                brave_key=os.environ.get("BRAVE_API_KEY") or None,
                state=args.enrichment_state,
                contact_fallback=args.contact_fallback,
            )
            enrichment_stats = stats
            print(f"      Organizations processed: {stats['processed']:,}")
            print(f"      Official websites found: {stats['websites_found']:,}")
            print(f"        - by Brave Search: {stats['brave_matches']:,}")
            print(f"        - by OpenRouter web-search fallback: {stats['web_search_fallbacks']:,}")
            print(f"      OpenRouter contact fallbacks: {stats['contact_fallbacks']:,}")
            print(f"      Organizations classified by Jev: {stats['classified']:,}")
            print(f"      Survey answers kept (Jev skipped): {stats['survey_answers_kept']:,}")
            print(f"      Already enriched and skipped: {stats['skipped_existing']:,}")
            print(f"      Pending after this run: {stats['remaining']:,}")
            print(f"      Enrichment errors: {stats['failed']:,}")
            print("      Full request log: Supabase table api_log")
    except BaseException:
        # Enrichment stopped early (error, Brave key, Ctrl+C): keep the finished paid work.
        print(f"      Organizations saved to Supabase: {store.save_payload(payload):,}")
        raise

    print(f"[{phase_count}/{phase_count}] Validating and saving to Supabase...", flush=True)
    records, points, fallback_points = validate_map_dataset(payload)
    print(f"      Validated {records:,} records and {points:,} map points")
    print(f"      Approximate ZIP/city points: {fallback_points:,}")
    print(f"      Records without a map point: {records - points:,}")
    saved = store.save_payload(payload)
    print(f"      Organizations saved to Supabase: {saved:,}")
    return {"organizations": records, "map_points": points, "saved": saved, **enrichment_stats}


def serve_map(host: str, port: int) -> None:
    """Serve the static ``app`` directory until interrupted by the operator."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(DEFAULT_APP_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Map ready at http://{host}:{port}")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping map server.")
    finally:
        server.server_close()


def main() -> None:
    """Load local configuration, validate secrets, run stages, and optionally serve."""
    load_environment(PROJECT_ROOT / ".env")
    args = parse_args()
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"] + (["OPENROUTER_API_KEY"] if args.enrich_with_jev else [])
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing)}")
    run_pipeline(args)
    if not args.no_serve:
        serve_map(args.host, args.port)


if __name__ == "__main__":
    main()
