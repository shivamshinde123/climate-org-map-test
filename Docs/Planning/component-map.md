# Component Map

## Data components

- `main.py`: runs IRS ingestion, coordinate assignment, output validation, and the local map server in order.
- `scripts/build_irs_dataset.py`: reads IRS files and emits normalized, ungeocoded GeoJSON with null geometry.
- `scripts/category_crosswalk.py`: resolves IRS NTEE codes, ProPublica NTEE values, and equivalent external labels through one versioned source-to-GCC taxonomy.
- `scripts/geocode_organizations.py`: owns coordinate assignment, applying cached or live Census matches and deterministic state-level fallbacks.
- `scripts/enrich_organizations_with_jev.py`: discovers official websites with OpenAI web search, persists summaries and evidence, and sends all eight bounded schema decisions to Jev through OpenRouter in one request per organization.
- `scripts/normalize_external_data_without_llm.py`: deterministically converts external CSV, JSON, or GeoJSON records into the GCC schema without an LLM.
- `Data/ProPublica/category-crosswalk.json`: authoritative machine-readable mapping for category-level IRS, ProPublica, and equivalent external-source classifications.
- `Docs/Research and Requirements/NTEE_Codes_to_Consider.txt`: filter configuration.
- `Docs/Planning/irs-schema-classification.md`: exact deterministic IRS-to-GCC category rules and limitations.
- `app/data/organizations.geojson`: generated map data.
- `app/data/map-schema.json`: runtime field and filter vocabulary.
- `Data/Geocoding/census_geocodes.csv`: resumable geocoding cache.

## Frontend components

- Application shell: title, context, and data-quality notice.
- Search controls: text query, state and NTEE source facets, the eight documented schema filters, and reset.
- Summary strip: visible and total record counts.
- Results list: bounded list of matching organizations.
- Map: OpenStreetMap basemap, clusters, points, navigation controls, and IRS-detail tooltips.

## Test components

- Ingestion unit tests validate filtering, normalization, stable IDs, null build geometry, Census result application, and deterministic geocoder-owned fallback placement.
