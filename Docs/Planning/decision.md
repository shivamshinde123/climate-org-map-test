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

## 2026-11-08 — Verification from the GCC survey

An organization is shown as Verified when it answered the GCC climate-organization survey itself (survey `source_field` = `primary`, `verified` = Verified). Mentions of an organization in another respondent's answers (`survey_B`) do not verify it. Green Beverly (EIN 871173877) is the first: verified in every `gb_survey` file, while the compiled survey's `Not Verified` row is another respondent naming it. Survey verifications are kept in `Data/Survey/survey-verifications.json`, matched on EIN so they survive IRS rebuilds, and applied by `main.py` after enrichment on every run, since Jev never sees survey evidence and would reset them. The popup shows a "Verified by GCC" badge and hides the claim-and-verify link for verified organizations. No Cool Petaluma data was present in either survey export.

## 2026-11-06 — Cut enrichment cost: contact lookup off, Brave-result picker, gpt-5.4-nano

A full national run was projected at ~$420, about 55% of it the LLM web-search fallback, of which roughly two thirds is the fixed $0.01 search fee rather than tokens. Three changes: the paid contact lookup is now opt-in (`--contact-fallback`); when Brave's rules match nothing, a cheap model first picks the official site from Brave's already-paid results (`pick_from_brave`, no web search, cached in `picker-cache.jsonl`), and only a "none" answer pays for a web search; and the default `SEARCH_MODEL` is `openai/gpt-5.4-nano` ($0.20/$1.25 per M tokens vs $0.75/$4.50). Picker quality and the real fallback rate are not yet measured.

## 2026-11-06 — Flat green visual system replaces the paper-atlas look

The frontend now follows a flat, editorial green design system (catalogued on Refero Styles from seed.com's site; only the visual language is borrowed, no branding): Snow White `#fcfcf7` canvas, Forest Depths `#1c3a13` for text and primary actions, Eucalyptus `#698e79` as secondary accent, and Lime Pulse `#d3fa99` reserved for small emphasis (badges, single-organization pins). Inter 300 for headings with tight tracking and 400–500 for body, JetBrains Mono for NTEE codes (the source's own typeface is proprietary). No shadows, gradients or decorative borders; 8px inputs, 16px cards/popups, pill buttons and badges. The OSM basemap is fully desaturated because the palette allows no blues, reds or purples. Popup links became underlined "→" text links and "Claim and verify this listing" became the primary filled pill.

## 2026-11-05 — Summary, phone and fallback-link rules (discovery v7, contacts v2)

Summaries: every candidate (site meta description, the first substantial paragraphs, Brave snippet) is filtered — under 60 characters, PO-box/"mail a check", driving directions, cookie/copyright chrome, and any text containing a phone number or email (an officer roster became one club's summary) are rejected — and text naming the organization or describing its work is preferred. Summaries are trimmed to whole sentences within 320 characters. The OpenRouter discovery prompt now asks for one to three plain sentences about the organization and forbids mentioning websites, searching, matching or EINs (21 of 26 fallback summaries did before; 1 after). Without an own-domain match, a Brave result must now be the site's root page: a one-segment page such as `alaskaadvisor.com/bootlegger.html` had passed as "homepage-like".

Phones: `tel:` links are preferred; plain-text numbers count only when labelled as a phone and not a fax; numbers must be valid NANP and are stored as `(AAA) EEE-NNNN`. A website stored as a subpage of someone else's site (e.g. `caves.org/grotto/x`) gets no crawled contacts, since they belong to the host. The OpenRouter contact lookup must cite the official-site page a phone came from (`phone_source_url`); numbers without an on-domain source are dropped. `CONTACT_VERSION` lets contact rules be re-applied without re-running discovery.

Caching: OpenRouter web-search answers are cached separately (`websearch-cache.jsonl`, keyed by prompt version, model and identity), so discovery-rule changes re-score cached Brave results without re-paying for web searches.

Facebook: when no website is found, the organization's Facebook page is taken from cached Brave results (no API call) if its slug matches the name, and shown as a "Facebook page" popup link. `--no-contact-fallback` skips the paid contact lookup for crawler-blocked sites.

## 2026-11-05 — Recover hidden organizations with tolerant city matching; restore categories on rejection

243 organizations had no map point because their PO-box ZIP has no Census ZCTA and their IRS city name missed the Census place list. The IRS master file caps city names at 13 characters (`CHARLOTTESVLE`, `SALT LAKE CTY`) and the Census list uses official or consolidated names (`Boise City`, `Urban Honolulu`, `Nashville-Davidson metropolitan government (balance)`). When the exact match fails, `match_city` now compares normalized names (punctuation removed, IRS abbreviations expanded, `SAINT`→`ST`), then aliases (NYC boroughs), then unique whole-word prefix/containment, then truncation-only fuzzy matching (the IRS name must be an in-order subset of the Census name). Whole-word and subset rules were added after the plain versions produced `WATERS`→`Watersmeet` and `CEDAR BROOK`→`Clearbrook`. Result: 154 recovered, 89 remain hidden (neighborhoods, villages and unincorporated places outside the Census place list). No existing pin moved.

A category spot-check found records whose website was rejected on re-run still carried Jev categories chosen from the rejected page's evidence. Jev now snapshots the IRS-derived values it replaces (`pre_enrichment_categories`), and clearing a rejected record restores them.

## 2026-11-05 — Match Brave results on the organization's own domain (discovery v5)

A hand review of the first full Rhode Island run (106 organizations) found about a third of Brave's picks were pages *about* the organization — funder and grant databases, business-data sites, state registries, court records, news articles, volunteer listings — because the score only checked whether the name and city appeared in the result's title and snippet. The score now ignores pages that can't be official (`.gov`/`.mil`, an expanded funder/donation/news host list, `?…id=` listing queries) and a result is accepted only when its domain matches the name (a distinctive word, two adjacent words, or the full initials) and its text names the organization, or, without a domain match, when it is a homepage-like URL with a very strong text match. The state is matched as a whole word or full name (the old check matched the letters "ri" anywhere). "nonprofit" was dropped from the query because it steered results toward directories. Accepted own-domain links are normalized to the homepage. Brave responses and paid contact lookups are now cached so rule changes can be replayed without paying again. Re-run result: 83/106 websites with about 3 clearly wrong (≈4%) versus ~30 wrong before, at the same ~1.8 cents per organization. The re-run also exposed that a record rejected on re-run kept the previous run's website and contacts; non-found records now have those fields cleared.

## 2026-11-05 — Log every API request; Brave summaries from the homepage; contacts in the popup

Enrichment spends money across two providers, so every Brave and OpenRouter request and every routing decision is written to `Data/Logs/api-requests.jsonl` with full request and response bodies (keys redacted) for audit and cost tracking. Brave search snippets were too thin to serve as the popup summary or as Jev's evidence, so a Brave match now uses the matched site's own meta description as the summary and passes the snippet plus a homepage text excerpt to Jev (discovery version bumped to v2). A rejected Brave key previously fell back silently to paid OpenRouter search for every record; it now stops the run. `main.py` now passes `BRAVE_API_KEY`, which it previously ignored. The map popup now shows email, phone and contact-page links when enrichment found them.

A 5-organization pilot the same day found 2 of 5 "websites" were nonprofit directories (getholdings.com, greatnonprofits.org), one summary was a news headline, and two emails were wrong (a directory's support address and Cloudflare's `[email protected]` placeholder). Fixes (discovery version v4): a broader directory host list plus a path rule for EIN/slug listing pages and document links (`.pdf`, `.docx`, …), applied to both Brave and OpenRouter results; summaries fall back to the site's first substantial paragraph before the Brave snippet; Cloudflare-obfuscated emails are decoded; emails are kept only on the site's own domain or a free mailbox, and fallback contact pages only on the site's domain. `--enrichment-state` limits a run to one state so pilots can target an area reviewers know.

## 2026-11-03 — Replace the state-level fallback with ZIP and city centroids

Coastal pins were landing in the sea (for example in Beverly, MA) because the city fallback scattered points up to 0.025° (~2.8 km) from a centroid only ~1 km from shore. The scatter is now 0.005° (~550 m). A full Census run matched 14,380 of 20,577 addresses. The remaining records now fall back to the Census ZCTA (ZIP) centroid, then the city centroid. ZIP comes first because every record has a ZIP and it avoids the IRS's 13-character city-name truncations (`CHARLOTTESVLE`, `SALT LAKE CTY`) that made the city lookup miss. The state-level scatter was removed: it placed pins up to ~100 km away, which misleads more than it helps. Records matching neither ZIP nor city (243) get null geometry, `location_precision=unavailable`, and are hidden by the frontend. This supersedes the state-level parts of the 2026-09-27 coordinate-ownership entry.

## 2026-11-03 — Route all LLM calls through OpenRouter

The fallback website-discovery and contact-extraction calls moved from OpenAI's Responses API (`web_search` tool) to OpenRouter's Chat Completions API with the `web` plugin and strict `json_schema` output, using `openai/gpt-5.4-mini`. Live web search is kept because IRS records are stale and many small organizations are absent from model training data, so answers from model memory alone would be unreliable. The change leaves one LLM credential (`OPENROUTER_API_KEY`) for both search and Jev classification and lets the search model be swapped by changing an OpenRouter model ID. `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL` are retired in favour of `SEARCH_MODEL` and `SEARCH_BASE_URL`. This supersedes the OpenAI-specific fallback wording in the two 2026-10-28 entries above.

## 2026-10-28 — Make one versioned crosswalk authoritative across sources

IRS ingestion, ProPublica analysis, and generic external normalization now resolve category-level mappings through `Data/ProPublica/category-crosswalk.json` via `scripts/category_crosswalk.py`. Exact NTEE codes, code-bearing labels, and equivalent normalized NTEE labels share one classification lineage and record their mapping basis and version. Unsupported target dimensions remain `Unknown`. This supersedes the duplicated hard-coded category derivations in individual adapters while preserving separate evidence-based inference for organization type, audience, reach, and narrow climate keywords.
