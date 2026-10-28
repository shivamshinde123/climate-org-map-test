# Decision Log

## 2026-09-27 — Use IRS data for the first map slice

The initial application will use only the supplied IRS EO BMF state files. This enables map and ingestion development before additional sources are integrated.

## 2026-09-27 — Keep the map contract source-agnostic

The frontend will consume normalized property names instead of raw IRS columns so later sources can be merged behind the same interface.

## 2026-09-27 — Use approximate coordinates only as labeled placeholders

IRS data lacks latitude and longitude. The prototype will assign deterministic state-level visual positions and mark them as approximate. These points are unsuitable for claims about exact organization locations.

## 2026-09-27 — Start dependency-light

The first implementation uses Python's standard library and a static browser application. This reduces setup friction while core data and interaction decisions remain fluid.

## 2026-09-27 — Match the complete target schema in the IRS preview

The normalized IRS output contains all target schema fields even when IRS cannot supply a value. Unknown data remains empty or explicitly `Unknown`. The map exposes the eight documented filters and retains additional IRS fields for its tooltip.

## 2026-09-27 — Use Census batch geocoding instead of public Nominatim

The public OpenStreetMap Nominatim service discourages large bulk jobs. The U.S. Census batch geocoder accepts the IRS address structure, supports large batches, and returns address-range coordinates. Results and non-matches are cached by organization ID and normalized-address hash.

## 2026-09-27 — Keep filter options independent from current data values

The eight product filters read their full option vocabulary from `app/data/map-schema.json`. All valid schema options remain visible, but the interface shows the current record count and disables options with zero IRS records. Additional options become usable automatically when future sources populate them.

## 2026-09-27 — Preserve IRS categories and add an auditable GCC crosswalk

Raw NTEE codes and labels remain in the map data. Dedicated GCC-aligned fields drive all eight product filters. NTEE meaning provides climate, action, activity, and resilience signals; conservative name rules provide organization type, audience, and reach signals. Mapping method and confidence fields distinguish direct mappings from keyword-assisted classification.

## 2026-09-27 — Normalize filter values before publication

Filter values use one title-cased canonical representation. Case-only duplicates such as `adaptation` and `Adaptation` are collapsed, and malformed array-like Reach values are excluded from the runtime vocabulary.

## 2026-09-27 — Normalize every future source before merging

External source files pass through a deterministic source-agnostic normalizer before matching or publication. Recognized explicit source values take precedence over inference, and every output records the mapping version and method.

## 2026-09-27 — Retire the standalone OpenAI classifier

The earlier standalone OpenAI classification stage was removed after the enrichment design made Jev the authoritative classifier. OpenAI remains responsible only for official-website discovery, evidence extraction, and summary generation. The deterministic source normalizer remains available as the non-model fallback.

## 2026-09-27 — Move all coordinate generation into the geocoding stage

`build_irs_dataset.py` now emits null geometry and never creates temporary map points. `geocode_organizations.py` is the single owner of coordinates: it prefers cached or live Census address-range matches and falls back to deterministic state-level placement when no match is available. This supersedes the earlier decision to have the prototype builder assign approximate coordinates.

## 2026-09-27 — Provide one safe orchestration entry point

`main.py` runs the IRS build, coordinate assignment, GeoJSON validation, and local map server in sequence. It defaults to cached Census results plus state-level fallback and requires the explicit `--use-census` option before transmitting uncached IRS address fields.

## 2026-09-27 — Display enriched profiles with a verification path

Official organization websites and evidence-based summaries are stored in the existing `website_url` and `summary` fields and displayed in map popups when available. Every popup links to the GCC Google Form so an organization can be claimed or its information verified. Website enrichment alone does not change the record to `Verified`.

## 2026-09-27 — Make Jev the authoritative enrichment classifier

The generative search model is limited to official-website discovery, evidence extraction, and summary writing. It does not assign GCC categories. The evidence package is sent to TypeSafe Jev through OpenRouter's Decisions API, and Jev returns all eight controlled schema fields as typed `choice` answers in one call. The application stores Jev's complete probability distributions and request metadata. An official website is not verification, and initial thresholds must be evaluated on a human-labeled pilot.

## 2026-09-27 — Make all expensive processing incremental

Normal runs reuse an existing normalized dataset and complete coordinates. Website and Jev enrichment records the prompt and model versions on each organization and removes completed records before applying a run limit. Content-addressed caches remain a second protection against duplicate external calls. Reprocessing requires a changed version/model, an incomplete or failed record, or the explicit `--rebuild` option for base ingestion.

## 2026-10-28 — Make one versioned crosswalk authoritative across sources

IRS ingestion, ProPublica analysis, and generic external normalization now resolve category-level mappings through `Data/ProPublica/category-crosswalk.json` via `scripts/category_crosswalk.py`. Exact NTEE codes, code-bearing labels, and equivalent normalized NTEE labels share one classification lineage and record their mapping basis and version. Unsupported target dimensions remain `Unknown`. This supersedes the duplicated hard-coded category derivations in individual adapters while preserving separate evidence-based inference for organization type, audience, reach, and narrow climate keywords.
