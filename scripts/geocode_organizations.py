#!/usr/bin/env python3
"""Assign map coordinates to normalized organization records.

This stage is the only pipeline component responsible for geometry. It first
reuses address-keyed results from the local cache, optionally submits new
addresses to the U.S. Census batch geocoder, and falls back to a ZIP or city
centroid when no usable address match exists. Records with neither get no
point. Every fallback is explicitly labeled so the UI never implies
street-level precision.
"""

from __future__ import annotations

import argparse
import csv
import difflib
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
ZCTA_GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2023_Gazetteer/2023_Gaz_zcta_national.zip"
)
USER_AGENT = "GCC-Climate-Organization-Map/0.1 (batch geocoding)"
# 0.005° ≈ 550 m. Coastal centroids (e.g. Beverly, MA) sit ~1 km from shore,
# so a wider radius drops pins into the sea.
FALLBACK_SPREAD = 0.005


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
    fails so the pipeline degrades to fewer fallbacks instead of crashing.
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

    rows = _gazetteer_rows(GAZETTEER_URL, "city")
    if not rows:
        return {}

    # LSAD type suffixes appended to NAME (e.g. "Beverly city", "Abanda CDP").
    # We strip the most common ones so "BEVERLY CITY" matches as "BEVERLY".
    _PLACE_SUFFIXES = re.compile(
        r"\s+(city|town|village|borough|township|cdp|municipality"
        r"|plantation|gore|grant|location|reservation|district)$",
        re.IGNORECASE,
    )

    centroids = {}
    for row in rows:
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


def _gazetteer_rows(url: str, label: str) -> list[dict]:
    """Download one Census Gazetteer zip and return its tab-separated rows."""
    print(f"Downloading US {label} centroids (Census Gazetteer)...", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            txt_name = next(n for n in zf.namelist() if n.endswith(".txt"))
            content = zf.read(txt_name).decode("latin-1")
    except Exception as exc:
        print(f"      Warning: {label} centroids unavailable ({exc}).", flush=True)
        return []
    lines = content.splitlines()
    if not lines:
        return []
    # The header has trailing whitespace on the last column, which corrupts
    # DictReader keys, so field names are stripped before parsing.
    fieldnames = [f.strip() for f in lines[0].split("\t")]
    return list(csv.DictReader(io.StringIO("\n".join(lines[1:])), fieldnames=fieldnames, delimiter="\t"))


def load_zip_centroids(cache_path: Path) -> dict[str, tuple[float, float]]:
    """Return 5-digit ZIP → (latitude, longitude) from the Census ZCTA Gazetteer.

    ZCTAs approximate USPS ZIP codes; PO-box-only ZIPs have no ZCTA and fall
    through to the city lookup.
    """
    centroids: dict[str, tuple[float, float]] = {}
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                centroids[row["zip"]] = (float(row["latitude"]), float(row["longitude"]))
        return centroids

    for row in _gazetteer_rows(ZCTA_GAZETTEER_URL, "ZIP"):
        try:
            centroids[row["GEOID"].strip()] = (
                float(row["INTPTLAT"].strip()),
                float(row["INTPTLONG"].strip()),
            )
        except (KeyError, ValueError, AttributeError):
            continue
    if not centroids:
        return {}

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["zip", "latitude", "longitude"])
        writer.writeheader()
        for zip_code, (lat, lng) in sorted(centroids.items()):
            writer.writerow({"zip": zip_code, "latitude": lat, "longitude": lng})
    print(f"      Cached {len(centroids):,} ZIP centroids.", flush=True)
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


def _scatter_around(
    latitude: float, longitude: float, seed: str, spread: float
) -> tuple[float, float]:
    """Return a stable point within `spread` degrees of (latitude, longitude).

    The record identifier seeds a blake2b hash, so an unchanged input receives
    the same point on every pipeline run.
    """
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=16).digest()
    angle_unit = int.from_bytes(digest[:8], "big") / (2**64 - 1)
    radius_unit = int.from_bytes(digest[8:], "big") / (2**64 - 1)
    angle = angle_unit * math.tau
    radius = math.sqrt(radius_unit) * spread
    latitude += math.sin(angle) * radius
    longitude += math.cos(angle) * radius / max(math.cos(math.radians(latitude)), 0.35)
    return round(longitude, 6), round(latitude, 6)


# The IRS master file caps city names at 13 characters, so long names arrive
# abbreviated ("COLORADO SPGS", "SALT LAKE CTY") or with letters dropped.
_CITY_ABBREVIATIONS = {
    "CTY": "CITY", "SPGS": "SPRINGS", "SPRGS": "SPRINGS", "SPG": "SPRINGS", "BCH": "BEACH",
    "HTS": "HEIGHTS", "HGTS": "HEIGHTS", "HLS": "HILLS", "PT": "POINT", "FT": "FORT",
    "MT": "MOUNT", "MTN": "MOUNTAIN", "JCT": "JUNCTION", "LK": "LAKE", "VLG": "VILLAGE",
    "CTR": "CENTER", "TWP": "TOWNSHIP", "PK": "PARK", "GRV": "GROVE", "HBR": "HARBOR",
    "CRK": "CREEK", "VLY": "VALLEY", "N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST",
    "SAINT": "ST", "SAINTE": "STE",
}
# Places the Census list folds into a larger city.
_CITY_ALIASES = {
    ("BROOKLYN", "NY"): "NEWYORK", ("BRONX", "NY"): "NEWYORK", ("QUEENS", "NY"): "NEWYORK",
    ("STATENISLAND", "NY"): "NEWYORK", ("FLUSHING", "NY"): "NEWYORK", ("JAMAICA", "NY"): "NEWYORK",
    ("ASTORIA", "NY"): "NEWYORK", ("LONGISLANDCITY", "NY"): "NEWYORK",
    ("HONOLULU", "HI"): "URBANHONOLULU",
}


def _is_subsequence(short: str, long: str) -> bool:
    letters = iter(long)
    return all(char in letters for char in short)


def _city_tokens(name: str) -> list[str]:
    tokens = re.split(r"[^A-Z0-9]+", name.upper())
    return [_CITY_ABBREVIATIONS.get(token, token) for token in tokens if token]


def city_key(name: str) -> str:
    """Normalize a city name so IRS and Census spellings compare equal."""
    return "".join(_city_tokens(name))


def _whole_word_runs(name: str) -> set[str]:
    """Every run of consecutive words in a name, joined ("BOISE", "BOISECITY", "CITY")."""
    tokens = _city_tokens(name)
    return {"".join(tokens[i:j]) for i in range(len(tokens)) for j in range(i + 1, len(tokens) + 1)}


def match_city(
    city: str, state: str, city_centroids: dict[tuple[str, str], tuple[float, float]]
) -> tuple[float, float] | None:
    """Find a city centroid despite IRS truncation, abbreviations and Census naming.

    Exact matches are handled by the caller; this runs only for misses, so the
    per-state scan stays cheap.
    """
    names = {city_key(c): c for (c, s) in city_centroids if s == state}
    keyed = {k: city_centroids[(c, state)] for k, c in names.items()}
    key = city_key(city)
    if not key or not keyed:
        return None
    if key in keyed:
        return keyed[key]
    alias = _CITY_ALIASES.get((key, state))
    if alias in keyed:
        return keyed[alias]
    for test, minimum in (
        # Whole words only, so WATERS never becomes WATERSMEET.
        (lambda k: k.startswith(key) and key in _whole_word_runs(names[k]), 5),  # BOISE -> BOISE CITY
        (lambda k: key in _whole_word_runs(names[k]), 6),  # VENTURA -> SAN BUENAVENTURA (VENTURA)
        # Census strips "city"/"town" suffixes: CARSON CITY -> CARSON
        (lambda k: len(k) >= 5 and key.startswith(k) and key[len(k):] in ("CITY", "TOWN", "VILLAGE"), 0),
    ):
        found = [k for k in keyed if test(k)]
        if len(key) >= minimum and len(found) == 1:
            return keyed[found[0]]
    # Truncation only drops letters, so the IRS name must be an in-order subset
    # of the Census name; plain fuzzy matching paired CEDAR BROOK with CLEARBROOK.
    truncated = [k for k in keyed if k[0] == key[0] and _is_subsequence(key, k)]
    close = difflib.get_close_matches(key, truncated, n=1, cutoff=0.85)
    return keyed[close[0]] if close else None


def apply_fallback(
    feature: dict,
    city_centroids: dict[tuple[str, str], tuple[float, float]] | None = None,
    zip_centroids: dict[str, tuple[float, float]] | None = None,
) -> bool:
    """Apply labeled approximate geometry when no Census address match exists.

    Tries the ZIP centroid, then the city centroid. A record matching neither
    gets null geometry and is left off the map rather than placed somewhere
    misleading.
    """
    properties = feature["properties"]
    seed = str(properties.get("source_id") or properties.get("id") or properties.get("name"))
    zip_code = str(properties.get("postal_code", "")).strip()[:5]
    city = str(properties.get("city", "")).strip().upper()
    state_key = str(properties.get("state", "")).strip().upper()

    center, precision, area = None, "", ""
    if zip_centroids and zip_code in zip_centroids:
        center, precision, area = zip_centroids[zip_code], "zip_level_fallback", f"ZIP {zip_code}"
    elif city_centroids and city and state_key:
        center = city_centroids.get((city, state_key)) or match_city(city, state_key, city_centroids)
        precision = "city_level_fallback"
        area = f"{properties.get('city', city).title()}, {state_key}"

    if center is None:
        feature["geometry"] = None
        properties["latitude"] = ""
        properties["longitude"] = ""
        properties["location_precision"] = "unavailable"
        properties["notes"] = "No geocoded, ZIP, or city location is available."
        return False

    # Scatter slightly so organizations sharing a centroid don't stack.
    longitude, latitude = _scatter_around(center[0], center[1], seed, FALLBACK_SPREAD)
    feature["geometry"] = {"type": "Point", "coordinates": [longitude, latitude]}
    properties["longitude"] = longitude
    properties["latitude"] = latitude
    properties["location_precision"] = precision
    properties["notes"] = (
        f"Street address geocoding was unavailable; coordinates are near the center "
        f"of {area}, not the organization's exact location."
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
    applied Census matches, cached non-matches, and ZIP/city fallbacks.
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
    zip_centroids = load_zip_centroids(cache_path.parent / "zip_centroids.csv")

    # Resolve every feature through the same precedence chain: current cached
    # Census result first, then ZIP centroid, then city centroid, then no point.
    matched = 0
    unmatched = 0
    fallbacks = 0
    for feature in features:
        properties = feature["properties"]
        result = cache.get(properties["id"])
        if result is None or result.address_key != make_address_key(properties):
            properties.setdefault("geocoding_status", "Not_Submitted")
            if apply_fallback(feature, city_centroids, zip_centroids):
                fallbacks += 1
        elif apply_result(feature, result):
            matched += 1
        else:
            unmatched += 1
            if apply_fallback(feature, city_centroids, zip_centroids):
                fallbacks += 1

    metadata = payload.setdefault("metadata", {})
    metadata["location_notice"] = (
        "Coordinates were assigned by geocode_organizations.py. Census address-range "
        "matches are preferred; other organizations fall back to their ZIP centroid, "
        "then their city centroid. Organizations matching neither have no map point."
    )
    metadata["geocoding"] = {
        "provider": "US Census Geocoder",
        "mode": "fallback_only" if fallback_only else "census_then_zip_city_fallback",
        "matched": matched,
        "unmatched": unmatched,
        "approximate_fallbacks": fallbacks,
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
        help="Do not call the Census API; apply cached matches and ZIP/city fallbacks",
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
    print(f"ZIP/city fallbacks applied: {fallbacks:,}")


if __name__ == "__main__":
    main()

