# Data Extraction Specification

## IRS input

- Directory: `Data/` (a rebuild first downloads `https://www.irs.gov/pub/irs-soi/eo_{state}.csv` for 50 states + DC into `Data/IRS EO BMF/`, with `If-Modified-Since` so unchanged files are skipped; local copies are used if irs.gov is unreachable)
- Files: `eo_*.csv` discovered recursively below the input directory
- Encoding: Latin-1
- Classification field: `NTEE_CD`
- Allowed codes: one exact code per line in `Docs/Research and Requirements/NTEE_Codes_to_Consider.txt`

## Normalization

- Trim surrounding whitespace.
- Collapse repeated internal whitespace in display text.
- Preserve EIN as a string.
- Preserve ZIP extensions while allowing ZIP search.
- Generate stable IDs from source name and EIN.
- Keep source status and subsection values without inventing interpretations.

## Coordinates

The IRS builder assigns no coordinates. It emits `geometry=null`, empty latitude and longitude values, and `location_precision=ungeocoded`. Coordinate assignment is exclusively the responsibility of `geocode_organizations.py`. Census matches use `location_precision=census_address_range`; records requiring a map fallback use `location_precision=zip_level_fallback` or `city_level_fallback`, or `unavailable` with null geometry when neither matches, and remain `validated=false`.

## Initial GCC classification

Every output record contains the complete target schema. Fields unavailable from IRS remain empty or `Unknown`. IRS organizations are initially typed as `Nonprofit / Grassroots` and remain `Unverified`.

The source and aligned classifications are stored separately:

- `irs_category` combines the untouched NTEE code and IRS category label.
- `gcc_climate_category` contains GCC's aligned climate taxonomy value.
- `gcc_action_category` contains GCC's aligned action taxonomy value.
- `gcc_alignment_method` identifies whether the result came from the NTEE crosswalk alone or a specific organization-name keyword plus the crosswalk.
- `gcc_alignment_confidence` is `high` for direct NTEE mappings and `medium` for broad or keyword-assisted mappings.

All product filters use dedicated aligned fields: `gcc_organization_type`, `gcc_audience_focus`, `gcc_resilience`, `gcc_activity`, `gcc_action_category`, `gcc_climate_category`, `gcc_reach`, and `gcc_verification`.

The climate crosswalk uses direct NTEE mappings for Recycling, Energy, and Conservation codes. Specific name phrases identify Food & Food Waste, Transportation, Green Economics, Energy Efficiency, and Waste Reduction candidates. Remaining selected codes fall back to Environmental.

The action crosswalk maps only the explicit values in `Data/ProPublica/category-crosswalk.json`. Activity and resilience come from that same versioned entry rather than being re-derived by separate code. Unsupported dimensions remain `Unknown`; for example, general conservation does not imply Adaptation, and only C35 directly supplies a Mitigation candidate. These are provisional ingestion rules, not organization-verified claims.

`scripts/category_crosswalk.py` is the shared resolver for IRS, ProPublica, and equivalent external NTEE labels. It accepts an explicit NTEE code, a category string containing a code, or an exact punctuation-insensitive NTEE label. Every successful result records the resolved code, mapping basis, and crosswalk version. Unrecognized labels do not enter filter-facing fields.

Organization Type, Audience Focus, and Reach use conservative organization-name rules. Municipality, academic, coalition, business, government-affiliated, resident-facing, and geographic-scope terms are mapped only when explicit keywords are present; otherwise the values remain the IRS-appropriate nonprofit default or `unknown`. Their individual confidence fields are retained.

## Output

Rows in the Supabase `organizations` table (`main.py` saves new and changed records). The builder does not skip otherwise valid records merely because coordinates are unavailable.

## Geocoding

The normalized `address`, `city`, `state`, and `postal_code` values are submitted to the U.S. Census batch geocoder only when the geocoding command is run without `--fallback-only`. Successful matches receive `location_precision=census_address_range`. Cached matches are reusable in either mode. Missing, unmatched, or unsubmitted addresses are placed near their ZIP centroid, then city centroid, with a deterministic scatter of at most 0.005°; records matching neither receive null geometry. The cache prevents repeat submission of unchanged addresses.

## Future extraction

Website enrichment must persist the accepted official URL in `website_url` and an evidence-based plain-text description in `summary`. Website discovery, page extraction, and schema classification are separate stages so each accepted URL and summary can retain source evidence. Cross-source matching and canonical merging remain TBD.

The implemented enrichment stage uses OpenRouter web search only for official-site identity resolution, evidence extraction, and summary generation. It must not produce the filter classifications. The evidence is supplied as shared state to Jev through OpenRouter, where all eight controlled fields are evaluated as `choice` questions in one Decisions API request. Jev choices, confidence values, complete probability distributions, served model version, provider, request ID, and question version are retained for audit. Both stages use content-addressed caches.

## External source normalization

`scripts/normalize_external_data_without_llm.py` converts external CSV, JSON arrays, GeoJSON FeatureCollections, or JSON objects containing `records` into the 24-field GCC schema without an LLM.

The deterministic precedence is:

1. Recognized explicit source category value.
2. Shared NTEE crosswalk when an NTEE code, code-bearing label, or equivalent exact NTEE label is available.
3. Ordered organization-name keyword rules for climate-category refinement only.
4. `Unknown` when evidence remains insufficient.

Common field aliases are built in. A source-specific JSON field map can explicitly connect unusual source column names to GCC fields. Output records retain source name, source record ID, original source category, resolved source-category code, crosswalk basis and version, GCC-aligned values, stable ID, schema version, and mapping-method description.

