# Current Blockers and Remaining Work

Last reviewed: 2026-10-28

## Current status

The prototype is operational and deployed. `python main.py --no-serve` validates
20,577 organization records and 20,577 map points. The map is live on GitHub Pages
and auto-deploys on push to `main`/`master` via GitHub Actions. The automated test
suite passes all 19 tests.

The items below do not prevent the existing prototype from opening. They block
accurate locations, enriched organization profiles, additional data sources,
verified records, or production-scale operation.

## Immediate blockers

### 1. Street-level location accuracy

**Status:** Mostly resolved (2026-11-03 full Census run).

Current dataset evidence:

- 20,577 total organization records.
- 14,380 Census address-range matches.
- 4,815 ZIP-centroid and 1,293 city-centroid fallback points (scatter ≤ 0.005°).
- 89 records with no map point (PO-box ZIP plus a neighborhood, village or
  unincorporated place name outside the Census place list).
- The state-level fallback was removed: it put pins up to ~100 km from the
  organization, including in the sea.

Remaining work:

- [x] Run Census geocoding for the complete dataset.
- [ ] Review match and non-match quality manually.
- [ ] Confirm that address changes invalidate cached results correctly.
- [x] Recover no-point records with tolerant city matching (154 of 243 recovered).

Suggested pilot command:

```powershell
python main.py --use-census --limit 100 --no-serve
```

### 2. Website discovery and Jev enrichment

**Status:** Pipeline implemented; blocked pending API credentials and a live pilot.

The full three-stage enrichment pipeline is implemented and unit-tested:
- **Brave Search** (primary) — `scripts/website_discovery.py`; scores results by name, city, state, and `.org` domain; accepts matches ≥ 0.5 confidence.
- **OpenRouter web search** (fallback) — called only when Brave returns no confident match or `BRAVE_API_KEY` is absent.
- **Deterministic crawler** — checks `robots.txt`, fetches homepage + contact page, extracts `email`, `phone`, `contact_page_url`.
- **Jev classification** — all eight schema fields in one OpenRouter Decisions API call.

Current dataset evidence:

- API credentials are not yet configured in `.env`.
- 0 organizations have websites, emails, phones, or Jev classifications.
- No discovery or Jev cache exists yet.

Remaining work:

- [ ] Populate `BRAVE_API_KEY` and `OPENROUTER_API_KEY` in `.env`.
- [ ] Confirm the configured `SEARCH_MODEL` supports OpenRouter's `web` plugin with strict `json_schema` output.
- [ ] Confirm `typesafe/jev-1.13` is accessible through the OpenRouter Decisions endpoint.
- [ ] Run a 10-record paid enrichment pilot.
- [ ] Review Brave identity matches, crawled contacts, evidence, summaries, and all eight schema classifications.
- [ ] Confirm repeated runs skip completed records and do not repeat paid calls.
- [ ] Estimate cost and elapsed time from the pilot before increasing the limit.

Suggested pilot command:

```powershell
python main.py --enrich-with-jev --enrichment-limit 10 --no-serve
```

### 3. Classification quality gate

**Status:** Blocked pending human evaluation criteria and labeled examples.

The current IRS classifications are deterministic but provisional. The Jev path
is implemented and unit-tested with mocked responses, but it has not been tested
against live model responses or a human-labeled evaluation set. Model confidence
must not be treated as proof of correctness.

Remaining work:

- [ ] Create a representative human-labeled sample across NTEE codes, states,
      organization types, and organization-name patterns.
- [ ] Define acceptance criteria for each of the eight schema fields.
- [ ] Compare deterministic classifications with Jev classifications.
- [ ] Measure invalid, unsupported, and ambiguous classifications.
- [ ] Decide whether low-confidence Jev choices remain unpublished, become
      `Unknown`, or enter a manual-review queue.
- [ ] Version prompts, questions, and evaluation results whenever logic changes.

### 4. Cross-source organization merging

**Status:** Not implemented.

`scripts/normalize_external_data_without_llm.py` can normalize future CSV, JSON,
and GeoJSON sources, but there is no canonical merge stage yet. Adding another
source now would create normalized records without safely resolving duplicate or
conflicting organizations.

Remaining work:

- [ ] Define identity matching rules using EIN, normalized name, website domain,
      address, phone, and source identifiers.
- [ ] Define deterministic exact-match rules before introducing fuzzy matching.
- [ ] Define field-level source priority and conflict-resolution rules.
- [ ] Preserve every source observation and its provenance.
- [ ] Create a canonical organization record without losing source records.
- [ ] Add ambiguous matches to a manual-review queue.
- [ ] Add merge, split, and duplicate-resolution tests.
- [ ] Implement the future merge step shown in the project flow diagram.

### 5. Verification workflow

**Status:** Only the outbound Google Form link is implemented.

Every tooltip links to the GCC claim-and-verification form, but responses are not
currently imported, matched, reviewed, or applied to map records. All 20,577
current records are `Not Verified`.

Remaining work:

- [ ] Define the Google Form response schema and required identifiers.
- [ ] Decide how submissions match an existing organization.
- [ ] Build an authenticated reviewer workflow or documented manual process.
- [ ] Store the reviewer, timestamp, evidence, and approved changes.
- [ ] Prevent automated enrichment from overwriting verified data.
- [ ] Publish approved changes and retain change history.
- [ ] Define processes for rejected, disputed, and duplicate submissions.

## Engineering work before production

### 6. Dataset delivery and browser performance

The current browser downloads one approximately 26 MB GeoJSON file (reduced from
~37 MB after removing redundant and internal-only fields) and performs all
filtering locally. This is acceptable for the present prototype but will become
increasingly expensive as enriched fields and sources are added.

- [ ] Measure initial load, parsing, filtering, and map-rendering performance on
      typical desktop and mobile devices.
- [ ] Remove internal-only fields from the public map payload where appropriate.
- [ ] Evaluate compressed delivery as an immediate optimization.
- [ ] Select a production approach such as vector tiles, paginated/spatial APIs,
      or server-side queries.
- [ ] Add loading, timeout, and partial-failure behavior for production delivery.

### 7. Production basemap and asset hosting

The prototype uses public OpenStreetMap raster tiles and loads MapLibre assets
from a public CDN. These services are suitable for development but are not an
assumed production service agreement.

- [ ] Review OpenStreetMap tile usage requirements and expected traffic.
- [ ] Select a production tile provider or hosted tile strategy.
- [ ] Self-host or bundle frontend dependencies where appropriate.
- [ ] Add monitoring for tile, data, and asset failures.

### 8. Persistence and administration

The project currently uses generated GeoJSON and append-only cache files rather
than an application database.

- [ ] Select a database and deployment architecture.
- [ ] Implement the logical entities described in
      `Docs/Planning/database-schema.md`.
- [ ] Add migrations, constraints, indexes, backups, and restore procedures.
- [ ] Add authentication and authorization for reviewers and administrators.
- [ ] Add auditable organization and classification change history.

### 9. Testing and operational readiness

- [ ] Add a live API smoke test for OpenRouter website discovery.
- [ ] Add a live API smoke test for Jev through OpenRouter.
- [ ] Add a controlled Census geocoding integration test.
- [ ] Add browser tests for filtering, clusters, popup scrolling, website links,
      and the verification link.
- [ ] Test keyboard navigation and screen-reader behavior.
- [ ] Add performance tests for the complete dataset.
- [ ] Add continuous integration for Python tests and JavaScript syntax checks.
- [ ] Define deployment, rollback, monitoring, and incident procedures.

## Recommended execution order

1. Configure credentials and run the 10-record website/Jev pilot.
2. Run a 100-record Census geocoding pilot and review match quality.
3. Build and label a representative classification evaluation set.
4. Approve or revise the Jev questions and deterministic fallback rules.
5. Complete geocoding and enrichment in controlled incremental batches.
6. Design and implement canonical cross-source matching and merging.
7. Connect verification submissions to a review and publication workflow.
8. Replace the large static-file delivery model before adding substantial new
   data volume.
9. Establish the production database, hosting, security, and operational stack.

## Confirmed working today

- [x] IRS source discovery and exact NTEE filtering.
- [x] Normalized source-agnostic map fields.
- [x] Deterministic IRS-to-schema category alignment via versioned crosswalk.
- [x] Deterministic external-source normalizer.
- [x] Stable organization IDs with no duplicates in the current output.
- [x] Geocoder-owned coordinate assignment and labeled state fallbacks.
- [x] OpenStreetMap basemap rendered through MapLibre.
- [x] Client-side search and schema-aligned filters.
- [x] Clustered markers and organization tooltips.
- [x] Optional website, summary, email, phone, and verification-link tooltip support.
- [x] Brave Search primary discovery with OpenRouter web-search fallback.
- [x] Deterministic contact crawler (email, phone, contact page) respecting robots.txt.
- [x] Incremental cache and skip logic in the enrichment implementation.
- [x] One orchestration entry point in `main.py`.
- [x] GitHub Actions auto-deploy to GitHub Pages on push.
- [x] Dataset validation and 19 passing automated tests.

## Related documentation

- `README.md`
- `Docs/Planning/flow.md`
- `Docs/Planning/decision.md`
- `Docs/Planning/data-extraction-specification.md`
- `Docs/Planning/database-schema.md`
- `Docs/Planning/irs-schema-classification.md`
