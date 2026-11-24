#!/usr/bin/env python3
"""Build the normalized IRS foundation used by the map.

The IRS EO BMF is identity and filing data, not a finished directory.  This
module filters configured environmental NTEE codes, maps each row into the
source-agnostic public schema, assigns stable IDs, and records a conservative
deterministic classification.  It deliberately emits null geometry; coordinate
ownership belongs to ``geocode_organizations.py``.

The classification rules are provisional and auditable.  They keep the map
usable before evidence enrichment, but Jev may later replace the public GCC
values while the original NTEE fields remain intact.
"""

from __future__ import annotations

import csv
import email.utils
import hashlib
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

try:
    from .category_crosswalk import resolve_source_category
except ImportError:  # Allows direct execution from the repository root.
    from category_crosswalk import resolve_source_category  # type: ignore


IRS_SOURCE_URL = (
    "https://www.irs.gov/charities-non-profits/"
    "exempt-organizations-business-master-file-extract-eo-bmf"
)

# One EO BMF extract per state, published by the IRS about monthly.
IRS_FILE_URL = "https://www.irs.gov/pub/irs-soi/eo_{}.csv"
IRS_STATES = (
    "ak al ar az ca co ct dc de fl ga hi ia id il in ks ky la ma md me mi mn mo ms mt nc nd ne "
    "nh nj nm nv ny oh ok or pa ri sc sd tn tx ut va vt wa wi wv wy"
).split()


def download_irs_files(directory: Path) -> int:
    """Fetch every state's EO BMF file from irs.gov into ``directory``; return how many changed.

    A file already present is only downloaded again when the IRS has published a
    newer one (``If-Modified-Since`` -> HTTP 304). If irs.gov can't be reached,
    the local copy is used with a warning; a missing file is an error.
    """
    directory.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for state in IRS_STATES:
        path = directory / f"eo_{state}.csv"
        request = urllib.request.Request(IRS_FILE_URL.format(state), headers={"User-Agent": "climate-org-map/1.0"})
        if path.exists():
            request.add_header("If-Modified-Since", email.utils.formatdate(path.stat().st_mtime, usegmt=True))
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                temporary = path.with_name(path.name + ".tmp")
                with temporary.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
                temporary.replace(path)
            downloaded += 1
        except urllib.error.HTTPError as error:
            if error.code != 304:
                if not path.exists():
                    raise
                print(f"      Warning: {path.name} not refreshed (HTTP {error.code}); using the local copy.", flush=True)
        except (urllib.error.URLError, TimeoutError) as error:
            if not path.exists():
                raise
            print(f"      Warning: {path.name} not refreshed ({error}); using the local copy.", flush=True)
    return downloaded


# Only codes selected by the project requirements are described here.  The
# external text file remains the actual inclusion configuration.
NTEE_LABELS: dict[str, str] = {
    "C00": "Environment (General)",
    "C01": "Alliance/Advocacy Organizations",
    "C03": "Professional Societies and Associations",
    "C05": "Research Institutes and Public Policy Analysis",
    "C12": "Fund Raising and/or Fund Distribution",
    "C19": "Support N.E.C.",
    "C20": "Pollution Abatement and Control",
    "C27": "Recycling",
    "C30": "Natural Resources Conservation and Protection",
    "C32": "Water Resource and Wetlands Conservation",
    "C34": "Land Resources Conservation",
    "C35": "Energy Resources Conservation and Development",
    "C36": "Forest Conservation",
    "C40": "Botanical, Horticultural, and Landscape Services",
    "C50": "Environmental Beautification and Open Spaces",
    "C60": "Environmental Education and Outdoor Survival Programs",
    "C99": "Environment N.E.C.",
}


# Ordered keyword groups refine broad NTEE categories when an organization's
# legal name contains unusually specific evidence.  Order matters: the first
# matching group wins, which keeps results deterministic.
CLIMATE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "Food & Food Waste",
        ("food waste", "compost", "community garden", "farm", "farming", "agriculture"),
    ),
    (
        "Transportation",
        ("transit", "transportation", "bicycle", "cycling", "pedestrian", "mobility", "electric vehicle"),
    ),
    (
        "Green Economics",
        ("green business", "sustainable business", "local economy", "green investment", "green investing"),
    ),
    (
        "Energy Efficiency",
        ("solar", "renewable energy", "clean energy", "energy efficiency", "weatherization", "electrification"),
    ),
    (
        "Waste Reduction",
        ("recycling", "recycle", "reuse", "repair cafe", "zero waste", "waste reduction"),
    ),
]

STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina",
    "SD": "south dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}


def infer_organization_type(name: str) -> tuple[str, str]:
    """Infer one provisional organization type from conservative name signals.

    Returns ``(controlled_value, confidence)``.  IRS-selected entities default
    to nonprofit/grassroots, while more specific types require explicit words.
    """
    normalized = name.casefold()
    if any(term in normalized for term in ("university", " college", "academic", "school of")):
        return "Academic", "medium"
    if any(term in normalized for term in ("city of ", "town of ", "village of ", "municipality of ")):
        return "Municipality", "medium"
    if any(term in normalized for term in ("authority", "commission", "public district", "government council")):
        return "Municipality", "medium"
    if any(term in normalized for term in ("coalition", " alliance", " network")):
        return "Coalition", "medium"
    if any(term in normalized for term in ("chamber of commerce", "business council", "business association")):
        return "Business", "medium"
    return "Nonprofit / Grassroots", "high"


def infer_audience(name: str, organization_type: str) -> tuple[str, str]:
    """Infer a single target audience from entity type and name evidence."""
    normalized = name.casefold()
    if organization_type == "Business":
        return "Businesses", "medium"
    if organization_type == "Municipality":
        return "Municipality", "medium"
    if any(
        term in normalized
        for term in ("community", "citizen", "resident", "neighborhood", "friends of", "public education")
    ):
        return "Residents", "medium"
    return "Unknown", "low"


def infer_reach(name: str, state: str, organization_type: str) -> tuple[str, str]:
    """Infer geographic scope without treating the mailing address as service area."""
    normalized = name.casefold()
    if organization_type == "Municipality":
        return "Town / City", "medium"
    # The GCC schema has no Global reach; State / National is its widest option.
    if any(term in normalized for term in (
        "global", "international", "worldwide", "world ", "national", "american", "united states", "usa ",
    )):
        return "State / National", "medium"
    state_name = STATE_NAMES.get(state, "")
    if state_name and state_name in normalized:
        return "State / National", "medium"
    if any(term in normalized for term in ("regional", "region ", "county", "multi-county")):
        return "Regional", "medium"
    if any(term in normalized for term in ("community", "neighborhood", "local ", "friends of")):
        return "Town / City", "medium"
    return "Unknown", "low"


def gcc_classification(
    ntee_code: str,
    organization_name: str,
    state: str = "",
    source_category: str = "",
) -> dict[str, str]:
    """Crosswalk one IRS category into every provisional GCC filter field.

    Climate, action, activity, and resilience come from the versioned shared
    crosswalk, with narrow organization-name keywords allowed to refine only
    climate category. Type, audience, and reach use separate name rules.
    Verification is never inferred from IRS presence.
    """
    normalized_name = organization_name.casefold()
    resolved = resolve_source_category(ntee_code, source_category)
    climate_category = resolved["climate_category"]
    action_category = resolved["action_category"]
    activity = resolved["activity"]
    resilience = resolved["resilience"]
    method = resolved["mapping_basis"]
    confidence = "medium"

    # A specific legal-name phrase is stronger evidence than a broad C-code.
    for category, keywords in CLIMATE_KEYWORDS:
        if any(keyword in normalized_name for keyword in keywords):
            climate_category = category
            method = f"organization name keyword + {resolved['mapping_basis']}"
            confidence = "medium"
            break

    if climate_category in {"Waste Reduction", "Energy Efficiency"}:
        confidence = "high"

    organization_type, organization_type_confidence = infer_organization_type(organization_name)
    audience, audience_confidence = infer_audience(organization_name, organization_type)
    reach, reach_confidence = infer_reach(organization_name, state, organization_type)

    return {
        "climate_category": climate_category,
        "action_category": action_category,
        "activity": activity,
        "resilience": resilience,
        "organization_type": organization_type,
        "organization_type_confidence": organization_type_confidence,
        "audience": audience,
        "audience_confidence": audience_confidence,
        "reach": reach,
        "reach_confidence": reach_confidence,
        "verification": "Not Verified",
        "method": method,
        "confidence": confidence,
        "source_category_code": resolved["ntee_code"],
        "source_category_label": resolved["ntee_label"],
        "mapping_version": resolved["mapping_version"],
    }


@dataclass
class BuildStats:
    """Counters reported by the streaming IRS ingestion pass."""
    source_rows: int = 0
    emitted: int = 0


def clean_text(value: str | None) -> str:
    """Trim and collapse whitespace without changing meaningful letter case."""
    return re.sub(r"\s+", " ", value or "").strip()


def load_codes(path: Path) -> set[str]:
    """Load the exact, case-normalized NTEE inclusion allowlist."""
    codes = {
        clean_text(line).upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if clean_text(line) and not clean_text(line).startswith("#")
    }
    if not codes:
        raise ValueError(f"No NTEE codes found in {path}")
    return codes


def stable_id(source: str, source_id: str) -> str:
    """Create a deterministic opaque ID without exposing source-specific syntax."""
    digest = hashlib.sha256(f"{source}:{source_id}".encode("utf-8")).hexdigest()
    return f"org_{digest[:16]}"


def row_to_feature(row: dict[str, str], selected_codes: set[str]) -> dict | None:
    """Convert an allowed IRS CSV row to a complete, ungeocoded GeoJSON feature.

    Returning ``None`` is the filtering contract for rows outside the configured
    NTEE set.  Empty IRS values remain empty rather than being fabricated.
    """
    code = clean_text(row.get("NTEE_CD")).upper()
    if code not in selected_codes:
        return None

    state = clean_text(row.get("STATE")).upper()
    ein = clean_text(row.get("EIN"))
    name = clean_text(row.get("NAME"))
    aligned = gcc_classification(code, name, state)
    organization_id = stable_id("irs_eo_bmf", ein or f"{name}:{state}")

    return {
        "type": "Feature",
        "id": organization_id,
        "geometry": None,
        "properties": {
            # Canonical map schema: every source adapter emits these names so
            # the frontend never needs to understand raw IRS columns.
            "id": organization_id,
            "name": name or "Unnamed organization",
            "website_url": "",
            "source_url": IRS_SOURCE_URL,
            "email": "",
            "phone": "",
            "address": clean_text(row.get("STREET")),
            "city": clean_text(row.get("CITY")),
            "state": state,
            "postal_code": clean_text(row.get("ZIP")),
            "latitude": "",
            "longitude": "",
            "summary": "",
            "notes": "Location has not been geocoded.",
            # Source provenance is retained even though the public popup is
            # intentionally minimal.  These fields support audit and merging.
            "source": "IRS EO BMF",
            "source_id": ein,
            "ntee_code": code,
            "ntee_label": NTEE_LABELS.get(code, code),
            "irs_category": f"{code} - {NTEE_LABELS.get(code, code)}",
            "gcc_climate_category": aligned["climate_category"],
            "gcc_action_category": aligned["action_category"],
            "gcc_organization_type": aligned["organization_type"],
            "gcc_audience_focus": aligned["audience"],
            "gcc_resilience": aligned["resilience"],
            "gcc_activity": aligned["activity"],
            "gcc_reach": aligned["reach"],
            "gcc_verification": aligned["verification"],
            "in_care_of": clean_text(row.get("ICO")),
            "subsection": clean_text(row.get("SUBSECTION")),
            "irs_status": clean_text(row.get("STATUS")),
            "ruling_date": clean_text(row.get("RULING")),
            "tax_period": clean_text(row.get("TAX_PERIOD")),
            "asset_amount": clean_text(row.get("ASSET_AMT")),
            "income_amount": clean_text(row.get("INCOME_AMT")),
            "revenue_amount": clean_text(row.get("REVENUE_AMT")),
            "location_precision": "ungeocoded",
        },
    }


def iter_features(
    csv_paths: Iterable[Path], selected_codes: set[str], stats: BuildStats
) -> Iterator[dict]:
    """Stream selected features from every state file with schema validation."""
    for csv_path in csv_paths:
        with csv_path.open("r", encoding="latin-1", newline="") as stream:
            reader = csv.DictReader(stream)
            # Fail early on a changed or corrupt source layout; silently reading
            # missing columns would produce plausible-looking bad records.
            required = {"EIN", "NAME", "STREET", "CITY", "STATE", "ZIP", "NTEE_CD"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{csv_path} is missing columns: {sorted(missing)}")

            for row in reader:
                stats.source_rows += 1
                feature = row_to_feature(row, selected_codes)
                if feature is None:
                    continue
                stats.emitted += 1
                yield feature


def build_dataset(
    input_dir: Path,
    codes_path: Path,
    limit: int | None = None,
) -> tuple[dict, BuildStats]:
    """Build a normalized FeatureCollection (``main.py --rebuild`` saves it).

    The optional limit is applied after NTEE filtering, making it useful for UI
    pilots while preserving the same transformation logic as a full build.
    """
    selected_codes = load_codes(codes_path)
    csv_paths = sorted(input_dir.rglob("eo_*.csv"))
    if not csv_paths:
        raise FileNotFoundError(f"No eo_*.csv files found in {input_dir}")

    stats = BuildStats()
    features: list[dict] = []
    for feature in iter_features(csv_paths, selected_codes, stats):
        features.append(feature)
        if limit is not None and len(features) >= limit:
            break

    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "IRS Exempt Organizations Business Master File",
            "source_files": len(csv_paths),
            "record_count": len(features),
            "selected_ntee_codes": sorted(selected_codes),
            "location_notice": (
                "Records are emitted without geometry. Run geocode_organizations.py "
                "to assign Census coordinates or ZIP/city fallbacks."
            ),
        },
        "features": features,
    }

    return collection, stats

