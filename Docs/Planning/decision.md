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

## 2026-10-28 — Deploy the map to GitHub Pages via GitHub Actions

The `app/` directory is deployed automatically to GitHub Pages on every push to `main` or `master` using the official GitHub `actions/deploy-pages` workflow. The site is publicly accessible even though the source repository is private. URL-based cache-busting (`?v=...`) is used instead of `cache: "no-store"` so that browsers cache the GeoJSON normally but still receive the correct version when the query string changes. The GeoJSON payload was reduced from ~37 MB to ~26 MB by removing 17 redundant and internal-only fields from the IRS pipeline output.

## 2026-10-28 — Use Brave Search as the primary discovery path with OpenAI as fallback

`scripts/website_discovery.py` implements Brave Search as the main website-discovery method. Brave is cheaper and faster for unambiguous cases. The existing OpenAI web-search path is retained as the fallback: when Brave returns no result with a confidence score ≥ 0.5, the record is passed to the OpenAI Responses API. Both paths write to the same content-addressed cache, so no record is ever searched twice for the same identity and model configuration. A `BRAVE_API_KEY` is optional; when absent, the pipeline uses OpenAI for all records as before.

## 2026-10-28 — Extract contact details with a deterministic crawler and OpenAI fallback

After a website is confirmed, `website_discovery.crawl_for_contacts` fetches the homepage and the first same-domain contact page found through link-text matching. It checks `robots.txt` before each fetch and extracts `email`, `phone`, and `contact_page_url` from `mailto:` and `tel:` links first, then falls back to text regex. The function returns `accessible=False` when `robots.txt` denies the crawler or the site is unreachable. In that case, `enrich_organizations_with_jev` makes a second OpenAI web-search call using `contact_search_payload` and the low-cost `search_context_size: low` setting to surface contacts from OpenAI's cached index. No contact details are inferred or guessed. Named individual contacts are not stored. Contact fields remain blank when neither path finds a public organizational contact.

## 2026-11-03 — Replace the state-level fallback with ZIP and city centroids

Coastal pins were landing in the sea (for example in Beverly, MA) because the city fallback scattered points up to 0.025° (~2.8 km) from a centroid only ~1 km from shore. The scatter is now 0.005° (~550 m). A full Census run matched 14,380 of 20,577 addresses. The remaining records now fall back to the Census ZCTA (ZIP) centroid, then the city centroid. ZIP comes first because every record has a ZIP and it avoids the IRS's 13-character city-name truncations (`CHARLOTTESVLE`, `SALT LAKE CTY`) that made the city lookup miss. The state-level scatter was removed: it placed pins up to ~100 km away, which misleads more than it helps. Records matching neither ZIP nor city (243) get null geometry, `location_precision=unavailable`, and are hidden by the frontend. This supersedes the state-level parts of the 2026-09-27 coordinate-ownership entry.

## 2026-11-03 — Route all LLM calls through OpenRouter

The fallback website-discovery and contact-extraction calls moved from OpenAI's Responses API (`web_search` tool) to OpenRouter's Chat Completions API with the `web` plugin and strict `json_schema` output, using `openai/gpt-5.4-mini`. Live web search is kept because IRS records are stale and many small organizations are absent from model training data, so answers from model memory alone would be unreliable. The change leaves one LLM credential (`OPENROUTER_API_KEY`) for both search and Jev classification and lets the search model be swapped by changing an OpenRouter model ID. `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL` are retired in favour of `SEARCH_MODEL` and `SEARCH_BASE_URL`. This supersedes the OpenAI-specific fallback wording in the two 2026-10-28 entries above.

## 2026-10-28 — Make one versioned crosswalk authoritative across sources

IRS ingestion, ProPublica analysis, and generic external normalization now resolve category-level mappings through `Data/ProPublica/category-crosswalk.json` via `scripts/category_crosswalk.py`. Exact NTEE codes, code-bearing labels, and equivalent normalized NTEE labels share one classification lineage and record their mapping basis and version. Unsupported target dimensions remain `Unknown`. This supersedes the duplicated hard-coded category derivations in individual adapters while preserving separate evidence-based inference for organization type, audience, reach, and narrow climate keywords.
