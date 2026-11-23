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

## 2026-11-23 — Supabase database, public add form, admin page

At the project owner's request, organizations move into a Supabase table so new and verified organizations can be added, edited and deleted without editing files and pushing to GitHub. All current organizations are loaded; the pipeline keeps producing the GeoJSON and `scripts/sync_supabase.py` copies it in, never overwriting a row the admin or a visitor changed.

The map keeps loading the static GeoJSON and merges only rows changed outside the pipeline from Supabase on each visit. Reading all 20,600 rows from the database on every visit would be slow; the static file plus a small live overlay gives instant edits without a deploy.

Anyone can add an organization on `add.html` (form or CSV), but submissions are `pending` and can never be marked Verified; the owner, the only admin, approves or deletes them on `admin.html`. A public form that wrote straight to the map would let anyone publish spam or a fake "Verified" listing. The admin signs in with an emailed link (no password to manage), and database row-level security — not the page — enforces who can write, because the anon key is public.

Deleting a form-added organization removes its row. Deleting a pipeline organization keeps a `removed` marker instead, because the organization is still in the static GeoJSON and in the next sync; the marker hides it and stops the sync from restoring it.

Addresses are geocoded in the browser with the Census one-line geocoder through JSONP (it sends no CORS headers), matching the pipeline's geocoder. New organizations' filters are chosen directly from the GCC schema values, so no survey-answer mapping is needed. Work is on the `supabase-database` branch, which does not deploy until merged into `master`.

## 2026-11-23 — Add the remaining verified responses from the MAP Verification survey

The "MAP Verification - Localized Climate Action Survey (Responses)" workbook has four responses. Cool Future was already on the map. Boston Climate Action Network (42 Seaverns Ave, Boston, MA 02130) and Cool Petaluma (245 Kentucky St, Suite B, Petaluma, CA) were added to `Data/Survey/survey-organizations.csv` as verified survey organizations, pinned at their Census-geocoded street addresses, with filters taken from their own answers (the first listed topic and reach, as for Cool Future). Neither has an IRS record on the map. The "Loopy" response (first name "Test", website "None", an invalid address) is a test submission and was not added. Cool Petaluma shares Cool Future's address, so their pins overlap; both appear in the results list.

## 2026-11-11 — Final website survey updates verified organizations; latest data wins

The project owner's final survey workbook ("Website - Localized Climate Action Survey (Responses)", 19 responses) updates organizations already verified on the map. It does not remove anyone, because the owner paused the full replacement. Responses were matched to verified records by hand (for example "Climate Energy Action Center - Energy Navigators" is the Climate Economy Action Center of Addison County, and the "Multiple: Concord…" response is the Concord Climate Action Committee). Blank or "Unknown" fields were filled, and — by the owner's rule — where the survey disagrees with an existing value, the latest data wins; for an organization with two responses, the later one wins. The one exception is a website answer that does not load (Sustainable Lebanon's "sustainablelebanon/wordpress.com"), where the working address was kept.

Changes: Westford (55 Main St) and Concord (221 Nashawtuc Rd) are pinned at street addresses; CEAC moved to 14 Seminary St, Middlebury, with reach Town / City, climate topic Energy Efficiency and its Energy Navigators page as the website; Green Newton has its P.O. box and ZIP (placed at the ZIP centroid) and activity Action; Hamilton Environmental Impact Committee's activity is Advocacy; Cape Ann Climate Coalition's resilience is Both; HWCAT's is Mitigation; Concord's audience is Residents / Businesses; Westford's website is the address given in the survey. Everyday Climate Champions Podcast is in the survey but not on the map, so it was not added.

## 2026-11-10 — Every filter allows several values

At the project owner's request, every filter, State included, is a checkbox dropdown instead of a single-choice select. Within one filter a record matches if it has any checked value; across filters every filter must match, so "MA + CA" with "Businesses" shows organizations in either state that serve businesses. The control is a native `<details>` element with checkboxes, so it needs no library and the form's reset button still clears it. Counts next to each value are for the whole dataset, not the current filtered view, as before.

## 2026-11-10 — Filters follow the GCC schema exactly

The project owner supplied the GCC schema, and the filter values now match it. Climate categories drop "Conservation"; that work maps to "Environmental", whose schema description already covers native plants and clean air and water (about 10,000 records). Reach drops "Global" (now "State / National", the widest option) and "Municipality" (now "Town / City"). Organization type drops "Municipal / Government-affiliated" (now "Municipality") and adds "Tribal/Indigenous" and "Committee"; the 7 survey town committees are "Committee". Audience focus adds the schema's four combinations ("Residents / Municipality", "Residents / Businesses", "Residents / Municipality / Businesses", "Municipality / Businesses") as single values, and the map's audience filter matches each part, so "Businesses" also shows "Residents / Businesses". Survey organizations keep their full combined answer instead of only the first. Climate values keep their short names; the schema's parenthetical descriptions became Jev's option descriptions. "Unknown" stays available for every field because missing evidence must be representable.

The IRS crosswalk (v2.1.0) and name rules produce only the new values. Instead of an IRS rebuild — whose enrichment overlay does not restore emails, phones or contact pages — the new rules were re-applied in place to records Jev has not classified, and every other stored value was mapped through the canonical synonyms. Jev re-classified the enriched Massachusetts and California records with the new questions (v2). The enrichment loop now skips the contact crawl when the site is unchanged and contacts are already current, because contacts do not depend on the category questions; that turned a multi-hour re-run into minutes. Rhode Island (discovery v7) was not re-run, because that would repeat paid website discovery; its stored values were mapped to the new options.

## 2026-11-10 — Full Massachusetts and California run; cap every site download

Massachusetts (651 IRS organizations) and California (2,704) were enriched with discovery v8 and `openai/gpt-5.4-nano`, keeping 5 OpenRouter web-search results and the paid contact fallback off. Results: MA 531 websites found, 25 ambiguous, 95 not found; CA 2,151 found, 124 ambiguous, 428 not found. The run cost about $40 — $23.43 on OpenRouter (web search $22.77 for 900 organizations, about 28%; picker $0.44; Jev $0.22) and about $16 for 3,251 Brave requests — above the $34 projection because the web-search share ran higher than the 20% seen in the 100-organization test. A 15-site California spot-check found 13 correct. One record (Southern Low Desert RCD Council) failed on a truncated model response and stays pending until the next run.

The California run hung for 1.5 hours on one site because `RobotFileParser.read()` has no timeout and `urlopen`'s timeout resets on every received byte. `robots.txt` is now fetched through `_fetch`, and each download is capped at twice its timeout in total. Paid results are cached per call, so the restart replayed finished organizations at no cost.

## 2026-11-09 — Brave query without legal suffix, 20 results, strict auto-accept (discovery v8)

A 50-organization Massachusetts pilot (gpt-5.4-nano) still sent 60% of organizations to the paid OpenRouter web search (~$0.025/call; the search fee dominates, the model barely matters). The cause was the Brave query: the quoted IRS legal name (`"BOSTON HARBOR NOW INC"`) matched directories, and only 5 results were requested, so the official site was rarely among them. The query now drops legal suffixes (INC, CORP, …; kept when fewer than 4 letters would remain) and is unquoted, and Brave returns 20 results (billed per request, so free). More results made the old one-distinctive-word domain rule accept neighbours and town sites (`marblehead.org`, `davisfarmland.com`), so automatic acceptance now requires `domain_is_exact_name` (the domain is essentially the name, or its initials, and its distinctive word is not just the town); everything else goes to the nano picker. Chamber-of-commerce hosts count as directories. On the same 100 MA organizations: paid search 20% (was 60%), websites 86% plus 8 Facebook pages, ~4 doubtful. Projected MA+CA cost ~$34 (was ~$65). The OpenRouter web search keeps 5 results by the owner's choice. Discovery version bumped to v8, so Rhode Island (v7) is re-processed only if run again.

## 2026-11-09 — Survey answers replace Jev categories for verified organizations

An organization that answered the GCC survey itself is a better source for its own categories than a model's guess, so the 9 survey-verified IRS organizations now take their category filters (type, audience, resilience, activity, climate topic, reach) from their survey row, stored as `survey_categories` in `Data/Survey/survey-verifications.json` (read from the `*_cleaned.csv` survey files; the `*_llm_enriched` files disagree on one row's verified flag). Mapping matches the survey-only organizations: a pair answered together becomes "Both", otherwise the first listed value; unanswered questions keep their current value. Action category has no survey question and is left as is. Survey verification is now applied before enrichment as well as after, and enrichment skips the Jev call for survey-verified records (website, summary and contact search still run) and counts them complete without a Jev result.

## 2026-11-08 — Add survey-only organizations to the map

About 27 organizations answered the GCC survey themselves but have no IRS record (town committees, chapters, one local business). They are listed in `Data/Survey/survey-organizations.csv` and added by `scripts/survey_organizations.py` as `source="GCC survey"`, verified, and pinned at the survey's street address where one was given (8 rows; geocoded once with the Census one-line geocoder, coordinates stored in the CSV, address shown in the popup). Rows with only a ZIP use the ZIP centroid; rows with no address use a town ZIP or the city centroid. An earlier same-day version withheld street addresses for privacy; the project owner decided to publish the survey addresses as given. Geocoding and enrichment skip these records so their pins, websites and survey categories are not overwritten; website/contact extraction for them is deferred. Excluded: ChargePoint (national company), plus two rows with conflicting or unclear locations.

## 2026-11-08 — Verification from the GCC survey

An organization is shown as Verified when it answered the GCC climate-organization survey itself (survey `source_field` = `primary`, `verified` = Verified). Mentions of an organization in another respondent's answers (`survey_B`) do not verify it. Green Beverly (EIN 871173877) is the first: verified in every `gb_survey` file, while the compiled survey's `Not Verified` row is another respondent naming it. Survey verifications are kept in `Data/Survey/survey-verifications.json`, matched on EIN so they survive IRS rebuilds, and applied by `main.py` after enrichment on every run, since Jev never sees survey evidence and would reset them. The popup shows a "Verified organization" badge and hides the claim-and-verify link for verified organizations. No Cool Petaluma data was present in either survey export.

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
