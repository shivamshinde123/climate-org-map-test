#!/usr/bin/env python3
"""Assign map coordinates to normalized organization records.

This stage is the only pipeline component responsible for geometry. It first
reuses address-keyed results from the local cache, optionally submits new
addresses to the U.S. Census batch geocoder, and finally assigns deterministic
state-level fallback points when no usable address match exists. Every fallback
is explicitly labeled so the UI never implies street-level precision.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_ENDPOINT = (
    "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
)
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2023_Gazetteer/2023_Gaz_place_national.zip"
)
USER_AGENT = "GCC-Climate-Organization-Map/0.1 (batch geocoding)"

# Approximate geographic centers used only when an address cannot be geocoded.
# The map never treats these values as authoritative organization locations.
STATE_CENTERS: dict[str, tuple[float, float]] = {
    "AK": (64.2008, -152.4937), "AL": (32.8067, -86.7911),
    "AR": (34.9697, -92.3731), "AZ": (33.7298, -111.4312),
    "CA": (36.1162, -119.6816), "CO": (39.0598, -105.3111),
    "CT": (41.5978, -72.7554), "DC": (38.9072, -77.0369),
    "DE": (39.3185, -75.5071), "FL": (27.7663, -81.6868),
    "GA": (33.0406, -83.6431), "HI": (21.0943, -157.4983),
    "IA": (42.0115, -93.2105), "ID": (44.2405, -114.4788),
    "IL": (40.3495, -88.9861), "IN": (39.8494, -86.2583),
    "KS": (38.5266, -96.7265), "KY": (37.6681, -84.6701),
    "LA": (31.1695, -91.8678), "MA": (42.2302, -71.5301),
    "MD": (39.0639, -76.8021), "ME": (44.6939, -69.3819),
    "MI": (43.3266, -84.5361), "MN": (45.6945, -93.9002),
    "MO": (38.4561, -92.2884), "MS": (32.7416, -89.6787),
    "MT": (46.9219, -110.4544), "NC": (35.6301, -79.8064),
    "ND": (47.5289, -99.7840), "NE": (41.1254, -98.2681),
    "NH": (43.4525, -71.5639), "NJ": (40.2989, -74.5210),
    "NM": (34.8405, -106.2485), "NV": (38.3135, -117.0554),
    "NY": (42.1657, -74.9481), "OH": (40.3888, -82.7649),
    "OK": (35.5653, -96.9289), "OR": (44.5720, -122.0709),
    "PA": (40.5908, -77.2098), "RI": (41.6809, -71.5118),
    "SC": (33.8569, -80.9450), "SD": (44.2998, -99.4388),
    "TN": (35.7478, -86.6923), "TX": (31.0545, -97.5635),
    "UT": (40.1500, -111.8624), "VA": (37.7693, -78.1700),
    "VT": (44.0459, -72.7107), "WA": (47.4009, -121.4905),
    "WI": (44.2685, -89.6165), "WV": (38.4912, -80.9545),
    "WY": (42.7560, -107.3025),
}

# Larger states need a wider deterministic scatter radius; compact states need
# a tighter radius to avoid placing their fallback points outside state bounds.
STATE_SPREAD: dict[str, float] = {
    "AK": 7.0, "CA": 3.2, "FL": 2.2, "HI": 1.1, "MT": 3.0,
    "TX": 4.2, "DC": 0.08, "DE": 0.22, "RI": 0.16, "CT": 0.3,
    "MA": 0.4, "MD": 0.45, "NJ": 0.35,
}


@dataclass
class GeocodeResult:
    """Serializable representation of one Census batch-response row."""
    id: str
    address_key: str
    match_status: str
    match_type: str
    matched_address: str
    longitude: str
    latitude: str
    tigerline_id: str
    side: str
    provider: str = "US Census Geocoder"
    geocoded_at: str = ""


def load_city_centroids(
    cache_path: Path,
) -> dict[tuple[str, str], tuple[float, float]]:
    """Return (CITY_UPPER, STATE) → (latitude, longitude) from the Census Gazetteer.

    Downloads and caches on first use. Returns an empty dict when the download
    fails so the pipeline degrades to state-level scatter instead of crashing.
    """
    if cache_path.exists():
        centroids: dict[tuple[str, str], tuple[float, float]] = {}
        with cache_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                centroids[(row["city"], row["state"])] = (
                    float(row["latitude"]),
                    float(row["longitude"]),
                )
        return centroids

    print("Downloading US city centroids (Census Gazetteer)...", flush=True)
    try:
        req = urllib.request.Request(GAZETTEER_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            txt_name = next(n for n in zf.namelist() if n.endswith(".txt"))
            content = zf.read(txt_name).decode("latin-1")
    except Exception as exc:
        print(
            f"      Warning: city centroids unavailable ({exc}); state fallback will be used.",
            flush=True,
        )
        return {}

    # The Gazetteer header has trailing whitespace on the last column, which
    # corrupts DictReader keys.  Strip every field name before parsing.
    lines = content.splitlines()
    if not lines:
        return {}
    fieldnames = [f.strip() for f in lines[0].split("\t")]
    body_text = "\n".join(lines[1:])

    # LSAD type suffixes appended to NAME (e.g. "Beverly city", "Abanda CDP").
    # We strip the most common ones so "BEVERLY CITY" matches as "BEVERLY".
    _PLACE_SUFFIXES = re.compile(
        r"\s+(city|town|village|borough|township|cdp|municipality"
        r"|plantation|gore|grant|location|reservation|district)$",
        re.IGNORECASE,
    )

    centroids = {}
    for row in csv.DictReader(io.StringIO(body_text), fieldnames=fieldnames, delimiter="\t"):
        state = row.get("USPS", "").strip().upper()
        raw_name = row.get("NAME", "").strip()
        name = _PLACE_SUFFIXES.sub("", raw_name).strip().upper()
        try:
            lat = float(row.get("INTPTLAT", "").strip())
            lng = float(row.get("INTPTLONG", "").strip())
        except (ValueError, AttributeError):
            continue
        if state and name:
            # Keep the first entry when a name appears more than once in a state
            # (e.g. there may be an "incorporated" and a "CDP" variant — we
            # prefer whichever comes first alphabetically in the file).
            centroids.setdefault((name, state), (lat, lng))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["city", "state", "latitude", "longitude"])
        writer.writeheader()
        for (city, state), (lat, lng) in sorted(centroids.items()):
            writer.writerow({"city": city, "state": state, "latitude": lat, "longitude": lng})
    print(f"      Cached {len(centroids):,} city centroids.", flush=True)
    return centroids


def normalized_address(properties: dict) -> tuple[str, str, str, str]:
    """Return normalized street, city, state, and ZIP values for matching."""
    return tuple(
        " ".join(str(properties.get(field, "")).split())
        for field in ("address", "city", "state", "postal_code")
    )


def make_address_key(properties: dict) -> str:
    """Create a stable cache key that changes whenever the address changes."""
    normalized = "|".join(part.upper() for part in normalized_address(properties))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def state_fallback_coordinates(state: str, seed: str) -> tuple[float, float] | None:
    """Return a stable state-level fallback point for an ungeocoded record.

    The record identifier supplies a reproducible angle and radius. This keeps
    overlapping organizations visually separable while guaranteeing that an
    unchanged input receives the same point on every pipeline run.
    """
    center = STATE_CENTERS.get(state)
    if center is None:
        return None
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=16).digest()
    angle_unit = int.from_bytes(digest[:8], "big") / (2**64 - 1)
    radius_unit = int.from_bytes(digest[8:], "big") / (2**64 - 1)
    angle = angle_unit * math.tau
    spread = STATE_SPREAD.get(state, 1.15)
    radius = math.sqrt(radius_unit) * spread
    latitude, longitude = center
    latitude += math.sin(angle) * radius
    longitude += math.cos(angle) * radius / max(math.cos(math.radians(latitude)), 0.35)
    return round(longitude, 6), round(latitude, 6)


def apply_state_fallback(
    feature: dict,
    city_centroids: dict[tuple[str, str], tuple[float, float]] | None = None,
) -> bool:
    """Apply labeled fallback geometry, preferring a city centroid when available.

    Tries (in order): city centroid from the Census Gazetteer, deterministic
    state-level scatter, then null geometry for completely unknown states.
    """
    properties = feature["properties"]
    seed = str(properties.get("source_id") or properties.get("id") or properties.get("name"))

    city = str(properties.get("city", "")).strip().upper()
    state_key = str(properties.get("state", "")).strip().upper()
    if city_centroids and city and state_key:
        city_coord = city_centroids.get((city, state_key))
        if city_coord:
            lat, lng = city_coord
            lng_r, lat_r = round(lng, 6), round(lat, 6)
            feature["geometry"] = {"type": "Point", "coordinates": [lng_r, lat_r]}
            properties["longitude"] = lng_r
            properties["latitude"] = lat_r
            properties["location_precision"] = "city_level_fallback"
            city_display = properties.get("city", city).title()
            properties["notes"] = (
                f"Street address geocoding was unavailable; coordinates are the "
                f"centroid of {city_display}, {state_key}."
            )
            return True

    coordinates = state_fallback_coordinates(str(properties.get("state", "")), seed)
    if coordinates is None:
        feature["geometry"] = None
        properties["latitude"] = ""
        properties["longitude"] = ""
        properties["location_precision"] = "unavailable"
        properties["notes"] = "No geocoded or state-level fallback location is available."
        return False
    longitude, latitude = coordinates
    feature["geometry"] = {"type": "Point", "coordinates": [longitude, latitude]}
    properties["longitude"] = longitude
    properties["latitude"] = latitude
    properties["location_precision"] = "state_level_fallback"
    properties["notes"] = (
        "Address geocoding was unavailable or unsuccessful; this is a deterministic "
        "state-level fallback point, not the organization's street location."
    )
    return True


def load_cache(path: Path) -> dict[str, GeocodeResult]:
    """Load the durable Census-result cache keyed by organization identifier."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as stream:
        return {
            row["id"]: GeocodeResult(**row)
            for row in csv.DictReader(stream)
        }


def save_cache(path: Path, results: dict[str, GeocodeResult]) -> None:
    """Atomically rewrite the cache so interrupted runs cannot corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fieldnames = list(GeocodeResult.__dataclass_fields__)
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for result_id in sorted(results):
            writer.writerow(asdict(results[result_id]))
    temporary.replace(path)


def chunks(items: list[dict], size: int) -> Iterable[list[dict]]:
    """Yield API-sized slices without copying the complete collection."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def build_batch_csv(features: list[dict]) -> bytes:
    """Encode features in the five-column Census batch-upload format."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for feature in features:
        properties = feature["properties"]
        street, city, state, postal_code = normalized_address(properties)
        writer.writerow([properties["id"], street, city, state, postal_code])
    return stream.getvalue().encode("utf-8")


def multipart_body(csv_bytes: bytes, boundary: str) -> bytes:
    """Construct the multipart request body expected by the Census endpoint."""
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="benchmark"\r\n\r\n',
        b"Public_AR_Current\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="addressFile"; filename="addresses.csv"\r\n',
        b"Content-Type: text/csv\r\n\r\n",
        csv_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts)


def submit_batch(
    features: list[dict], endpoint: str = DEFAULT_ENDPOINT, retries: int = 3
) -> str:
    """Submit one address batch, retrying transient network failures."""
    boundary = f"----gcc-climate-map-{uuid.uuid4().hex}"
    body = multipart_body(build_batch_csv(features), boundary)
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "User-Agent": USER_AGENT,
            "Accept": "text/csv",
        },
    )

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == retries:
                raise RuntimeError(f"Census geocoding failed after {retries} attempts") from error
            time.sleep(2**attempt)
    raise RuntimeError("Unreachable geocoding retry state")


def parse_batch_response(
    response_text: str, requested: dict[str, dict], timestamp: str
) -> dict[str, GeocodeResult]:
    """Parse Census CSV output and preserve explicit rows for missing results."""
    parsed: dict[str, GeocodeResult] = {}
    for row in csv.reader(io.StringIO(response_text)):
        if not row:
            continue
        padded = row + [""] * max(0, 8 - len(row))
        result_id = padded[0]
        if result_id not in requested:
            continue
        coordinates = [part.strip() for part in padded[5].split(",")]
        longitude = coordinates[0] if len(coordinates) == 2 else ""
        latitude = coordinates[1] if len(coordinates) == 2 else ""
        parsed[result_id] = GeocodeResult(
            id=result_id,
            address_key=make_address_key(requested[result_id]["properties"]),
            match_status=padded[2],
            match_type=padded[3],
            matched_address=padded[4],
            longitude=longitude,
            latitude=latitude,
            tigerline_id=padded[6],
            side=padded[7],
            geocoded_at=timestamp,
        )

    # Cache missing response rows as errors so an incomplete response is auditable.
    for result_id, feature in requested.items():
        if result_id not in parsed:
            parsed[result_id] = GeocodeResult(
                id=result_id,
                address_key=make_address_key(feature["properties"]),
                match_status="Response_Missing",
                match_type="",
                matched_address="",
                longitude="",
                latitude="",
                tigerline_id="",
                side="",
                geocoded_at=timestamp,
            )
    return parsed


def apply_result(feature: dict, result: GeocodeResult) -> bool:
    """Apply a valid Census point and its provenance fields to a feature."""
    properties = feature["properties"]
    properties["geocoding_provider"] = result.provider
    properties["geocoding_status"] = result.match_status
    properties["geocoding_match_type"] = result.match_type
    properties["geocoded_address"] = result.matched_address
    properties["geocoded_at"] = result.geocoded_at

    try:
        longitude = float(result.longitude)
        latitude = float(result.latitude)
    except ValueError:
        return False

    feature["geometry"] = {"type": "Point", "coordinates": [longitude, latitude]}
    properties["longitude"] = longitude
    properties["latitude"] = latitude
    properties["location_precision"] = "census_address_range"
    properties["notes"] = (
        "Address geocoded by the U.S. Census Geocoder; coordinates may be "
        "interpolated along an address range."
    )
    return True


def geocode_dataset(
    input_path: Path,
    output_path: Path,
    cache_path: Path,
    endpoint: str,
    batch_size: int,
    limit: int | None,
    fallback_only: bool = False,
) -> tuple[int, int, int, int]:
    """Geocode a GeoJSON dataset and write its completed geometry atomically.

    ``fallback_only`` disables network submissions but still consumes valid
    cached matches. The returned counts are, in order: newly submitted records,
    applied Census matches, cached non-matches, and state-level fallbacks.
    """
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    cache = load_cache(cache_path)

    # A cached value is reusable only while its address hash still matches.
    eligible: list[dict] = []
    for feature in features:
        properties = feature["properties"]
        street, _city, state, _postal_code = normalized_address(properties)
        if not street or not state:
            continue
        cached = cache.get(properties["id"])
        if cached and cached.address_key == make_address_key(properties):
            continue
        if not fallback_only:
            eligible.append(feature)
        if limit is not None and len(eligible) >= limit:
            break

    for index, batch in enumerate(chunks(eligible, batch_size), start=1):
        print(f"Submitting Census batch {index} ({len(batch):,} addresses)...", flush=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        requested = {feature["properties"]["id"]: feature for feature in batch}
        response_text = submit_batch(batch, endpoint)
        cache.update(parse_batch_response(response_text, requested, timestamp))
        # Persist after every batch so a later failure does not waste prior work.
        save_cache(cache_path, cache)
        print(f"Cached {len(cache):,} total geocoding results", flush=True)

    city_centroids = load_city_centroids(cache_path.parent / "city_centroids.csv")

    # Resolve every feature through the same precedence chain: current cached
    # Census result first, then city centroid, then state-level scatter.
    matched = 0
    unmatched = 0
    fallbacks = 0
    for feature in features:
        properties = feature["properties"]
        result = cache.get(properties["id"])
        if result is None or result.address_key != make_address_key(properties):
            properties.setdefault("geocoding_status", "Not_Submitted")
            if apply_state_fallback(feature, city_centroids):
                fallbacks += 1
        elif apply_result(feature, result):
            matched += 1
        else:
            unmatched += 1
            if apply_state_fallback(feature, city_centroids):
                fallbacks += 1

    metadata = payload.setdefault("metadata", {})
    metadata["location_notice"] = (
        "Coordinates were assigned by geocode_organizations.py. Census address-range "
        "matches are preferred; organizations without a usable street address fall back "
        "to their city centroid, and finally to a deterministic state-level scatter point."
    )
    metadata["geocoding"] = {
        "provider": "US Census Geocoder",
        "mode": "fallback_only" if fallback_only else "census_then_state_fallback",
        "matched": matched,
        "unmatched": unmatched,
        "state_level_fallbacks": fallbacks,
        "cached_results": len(cache),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    temporary.replace(output_path)
    return len(eligible), matched, unmatched, fallbacks


def parse_args() -> argparse.Namespace:
    """Parse and validate the geocoder command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("app/data/organizations.geojson"))
    parser.add_argument("--output", type=Path, default=Path("app/data/organizations.geojson"))
    parser.add_argument(
        "--cache", type=Path, default=Path("Data/Geocoding/census_geocodes.csv")
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--fallback-only",
        action="store_true",
        help="Do not call the Census API; apply cached matches and state-level fallbacks",
    )
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 10_000:
        parser.error("--batch-size must be between 1 and 10000")
    return args


def main() -> None:
    """Run the command-line geocoding stage and print an audit summary."""
    args = parse_args()
    submitted, matched, unmatched, fallbacks = geocode_dataset(
        args.input,
        args.output,
        args.cache,
        args.endpoint,
        args.batch_size,
        args.limit,
        args.fallback_only,
    )
    print(f"New addresses submitted: {submitted:,}")
    print(f"Coordinates applied: {matched:,}")
    print(f"Cached non-matches: {unmatched:,}")
    print(f"State-level fallbacks applied: {fallbacks:,}")


if __name__ == "__main__":
    main()

