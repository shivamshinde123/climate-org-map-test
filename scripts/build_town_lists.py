"""Build per-state town lists for the form's Town / City suggestions.

    python -m scripts.build_town_lists

Writes ``app/data/towns/<STATE>.json`` (a sorted list of names) from two Census
Gazetteer files: places (cities, towns, villages, CDPs) and county
subdivisions with a functioning government. The second adds the New England
and Mid-Atlantic towns that the place list leaves out. Suggestions only: the
forms accept any town name.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

try:
    from .geocode_organizations import GAZETTEER_URL, _gazetteer_rows
except ImportError:  # Allows direct execution from the scripts directory.
    from geocode_organizations import GAZETTEER_URL, _gazetteer_rows  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "app" / "data" / "towns"
COUSUB_URL = GAZETTEER_URL.replace("2023_Gaz_place_national", "2023_Gaz_cousubs_national")

# Census type words appended to names ("Beverly city", "Abanda CDP").
SUFFIX = re.compile(
    r"\s+(city|town|village|borough|township|cdp|municipality|plantation|gore|grant"
    r"|location|reservation|comunidad|zona urbana|city and borough|consolidated government"
    r"|metropolitan government|unified government|urban county)(\s*\(.*\))?$",
    re.IGNORECASE,
)
# County subdivisions that are real municipalities, not statistical areas.
MUNICIPAL = re.compile(r"\s(city|town|village|borough|township|plantation)$", re.IGNORECASE)


def clean(name: str, state: str = "") -> str:
    name = SUFFIX.sub("", name.strip()).strip()
    # Massachusetts towns with a city government are listed as "Agawam Town city".
    # Elsewhere "Town" can be part of the name (Charles Town, WV).
    return name.removesuffix(" Town") if state == "MA" else name


def town_lists(places: list[dict], cousubs: list[dict]) -> dict[str, list[str]]:
    towns: dict[str, set[str]] = defaultdict(set)
    for row in places:
        state = row["USPS"].strip()
        towns[state].add(clean(row["NAME"], state))
    for row in cousubs:
        name, state = row["NAME"].strip(), row["USPS"].strip()
        if row.get("FUNCSTAT", "").strip() == "A" and MUNICIPAL.search(name):
            towns[state].add(clean(name, state))
    return {state: sorted(names - {""}, key=str.casefold) for state, names in towns.items()}


def main() -> None:
    lists = town_lists(_gazetteer_rows(GAZETTEER_URL, "place"), _gazetteer_rows(COUSUB_URL, "county subdivision"))
    if not lists:
        raise SystemExit("No Census rows downloaded; town lists unchanged.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for state, names in lists.items():
        (OUTPUT_DIR / f"{state}.json").write_text(json.dumps(names, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(lists)} states, {sum(map(len, lists.values())):,} towns to {OUTPUT_DIR.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
