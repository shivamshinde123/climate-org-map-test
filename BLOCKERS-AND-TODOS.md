# Current Blockers and Remaining Work

Last reviewed: 2026-09-27

## Current status

The local IRS-based prototype is operational. `python main.py --no-serve`
successfully validates 20,577 organization records and 20,577 map points, and the
automated test suite currently passes all 18 tests.

The items below do not prevent the existing prototype from opening. They block
accurate locations, enriched organization profiles, additional data sources,
verified records, or production-scale operation.

## Immediate blockers

### 1. Street-level location accuracy

**Status:** Blocked pending live Census geocoding.

Current dataset evidence:

- 20,577 total organization records.
- 0 Census address-range matches.
- 20,577 deterministic state-level fallback points.
- No `Data/Geocoding/census_geocodes.csv` cache exists yet.

The source street, city, state, and ZIP fields are present, but the displayed
points are currently approximate state-level placements rather than organization
street locations.

Remaining work:

- [ ] Run a small live Census geocoding pilot.
- [ ] Review match and non-match quality manually.
- [ ] Confirm that address changes invalidate cached results correctly.
- [ ] Run Census geocoding for the complete dataset after pilot approval.
- [ ] Review the remaining fallback locations and determine whether another
      approved geocoding source is needed.

Suggested pilot command:

```powershell
python main.py --use-census --limit 100 --no-serve
```

### 2. Website discovery and Jev enrichment

**Status:** Blocked pending API credentials and a live pilot.

Current dataset evidence:

- `OPENAI_API_KEY` is not configured.
- `OPENROUTER_API_KEY` is not configured.
- 0 organization websites have been added.
- 0 organization summaries have been added.
- 0 organizations have been classified by Jev.
- No website-discovery or Jev cache exists yet.

Remaining work:

- [ ] Populate `OPENAI_API_KEY` and `OPENROUTER_API_KEY` in `.env`.
- [ ] Confirm the configured OpenAI search model can perform web search.
- [ ] Confirm `typesafe/jev-1.13` is accessible through the configured OpenRouter
      Decisions endpoint.
- [ ] Run a 10-record paid enrichment pilot.
- [ ] Review official-site identity matches, evidence, summaries, and all eight
      schema classifications.
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

The current browser downloads one approximately 36.58 MB GeoJSON file and
performs all filtering locally. This is acceptable for the present prototype but
will become increasingly expensive as enriched fields and sources are added.

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

- [ ] Add a live API smoke test for OpenAI website discovery.
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
- [x] Deterministic IRS-to-schema category alignment.
- [x] Deterministic external-source normalizer.
- [x] Stable organization IDs with no duplicates in the current output.
- [x] Geocoder-owned coordinate assignment and labeled state fallbacks.
- [x] OpenStreetMap basemap rendered through MapLibre.
- [x] Client-side search and schema-aligned filters.
- [x] Clustered markers and organization tooltips.
- [x] Optional website, summary, and verification-link tooltip support.
- [x] Incremental cache and skip logic in the enrichment implementation.
- [x] One orchestration entry point in `main.py`.
- [x] Dataset validation and 18 passing automated tests.

## Related documentation

- `README.md`
- `Docs/Planning/flow.md`
- `Docs/Planning/decision.md`
- `Docs/Planning/data-extraction-specification.md`
- `Docs/Planning/database-schema.md`
- `Docs/Planning/irs-schema-classification.md`
