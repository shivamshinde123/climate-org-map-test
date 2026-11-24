# Database Schema

## Current release

Organizations live in one Supabase (Postgres) table, created by `supabase/migrations/20261123000000_organizations.sql`. Supabase is the only data store: the map, the admin portal and the pipeline all read and write it, and no JSON data files remain (`20261124000000_database_only.sql`).

### `organizations`

| Column | Type | Notes |
|---|---|---|
| `id` | text, primary key | Same id as the map feature (`org_…` for IRS, `survey_…` for survey-only, `added_…` for form/CSV additions; `added_` ids hash name + state, so the same organization cannot be added twice). |
| `properties` | jsonb | Exactly the map feature's properties, so the pipeline, the map and the forms share one shape. |
| `review_status` | text | `pending` (visitor submission), `approved` (on the map), `removed` (deleted by the admin; kept only for pipeline rows), `rejected` (unused). |
| `updated_via` | text | Who last changed the row: `pipeline`, `admin`, `public_form`. |
| `created_at`, `updated_at` | timestamptz | `updated_at` is set by a trigger on every update. |
| `name`, `city`, `state`, `verification` | text, generated | Read-only copies of `properties` fields for admin search. |
| `map` | jsonb, generated | Compact array of the fields the map needs (order in `20261124010000_map_rows.sql`, matching `MAP_FIELDS` in `app/app.js`). `map_organizations()` returns these for every approved row in one call. |

Deleting: rows added through the forms are deleted outright. A pipeline row would be re-created by the next `--rebuild`, so a deleted pipeline row stays as `removed` / `admin`: the map and the pipeline skip it.

### `survey_responses`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, primary key | |
| `created_at` | timestamptz | |
| `connection` | text | `organization`, `municipality` or `individual` (the first question's answer). |
| `organization_id` | text | Map listing the survey was opened from ("Claim and verify"), if any. |
| `answers` | jsonb | Question id from `app/data/survey.json` → answer (text, or a list for check boxes). `_location` holds an exact point picked from the address suggestions. |
| `review_status` | text | `pending` (organization, waiting for the admin), `approved` (applied to the map), `research` (municipal or individual). |
| `applied_organization_id`, `reviewed_at` | text, timestamptz | Set when the admin verifies it. |

Access: visitors may only insert, with the status their connection requires (`pending` for organizations, `research` otherwise); only admins can read, change or delete. Created by `supabase/migrations/20261123020000_survey_responses.sql`.

### `pipeline_cache`

| Column | Type | Notes |
|---|---|---|
| `kind`, `key` | text, primary key | `kind` is `brave`, `discovery`, `websearch`, `picker`, `contact`, `jev` or `census`; `key` is the Brave query, a hash of the request, or (for `census`) the organization id, whose result carries the address hash it was geocoded from. |
| `result` | jsonb | The API answer. Brave results keep only `url`, `title` and `description`, the fields the matcher reads. |
| `created_at` | timestamptz | |

Paid API answers, so a rerun never pays twice for the same question. Service role only.

### `api_log`

`id` (identity), `created_at`, `entry` (jsonb): one row per Brave/OpenRouter request or routing decision, written by `scripts/api_log.py`. Request and response bodies are cut at 4,000 characters to keep the database small. Service role only.

### `pipeline_runs`

One row per pipeline run request (`supabase/migrations/20261124030000_pipeline_runs.sql`).

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity, primary key | |
| `kind` | text | `extract` (website, contacts, summary, Jev for one state) or `irs_refresh` (download IRS files, rebuild, geocode; no paid calls). |
| `state`, `org_limit` | text, integer | Required for `extract`. `org_limit` 1–1000 caps spend and keeps a run under GitHub's 6-hour job limit. |
| `status` | text | `queued` → `running` → `succeeded` / `failed`, or `cancelled` by an admin. A unique partial index allows only one `queued` or `running` row. |
| `requested_by` | text | Email from the admin's sign-in token (default). |
| `created_at`, `started_at`, `finished_at` | timestamptz | |
| `run_url`, `summary`, `error` | text, jsonb, text | Written by the GitHub run: log link, counts, failure message. |

`dispatch_request_id` (bigint) is pg_net's id for the GitHub start request: an `after insert` trigger (`dispatch_pipeline_run()`, migration `20261124040000`) posts `workflow_dispatch` for `pipeline.yml` on `master` with the row id, using the Vault secrets `github_dispatch_token` and `github_repo`; if either is missing the row is marked `failed` immediately. `pipeline_dispatch_result(run_id)` (admins only) returns GitHub's status code and message from `net._http_response` (204 = started; pg_net keeps answers 6 hours).

`queue_irs_refresh()` (pg_cron job `irs-refresh`, daily 09:00 UTC, migration `20261124050000`) inserts an `irs_refresh` row when no refresh succeeded in the last 28 days, none was queued in the last 20 hours, and no run is active.

Admins may read all rows, insert only `kind`, `state`, `org_limit` (column grants), and set a `queued` or `running` row to `cancelled` (for a run that never started or died). Everything else is written with the service role.

### `pipeline_settings`

One row (`id = true`): `discovery_version`, `search_model`, `jev_model`, `jev_questions_version`, `contact_version`, `updated_at`. Written by `enrich_payload` at the start of every extraction; admins can read it. `extraction_pending()` (admins only) returns `(state, pending)`: approved organizations an extraction would still process, the same rule as `enrichment_is_complete()` in Python. Checked equal per state on 2026-11-24 (17,223 pending).

### `admins`

`email` (primary key). Readable and writable only with the service role key. `scripts/sync_supabase.py` keeps it equal to `ADMIN_EMAILS` (adds and removes; an empty setting changes nothing).

### Access rules (row-level security)

- Anyone may read `approved` rows; the map loads all of them.
- Anyone may insert a row only if it is `pending`, `public_form`, `Not Verified`, and under 16 KB.
- An email in `admins` (checked by `is_admin()`) may read, change and delete every row.
- `sync_pipeline_organizations(rows jsonb)` is the pipeline's write. Pipeline rows take the pipeline's values; rows the admin or a visitor changed keep every non-empty value and only gain empty fields and the pipeline's bookkeeping fields (website discovery, Jev, contacts, geocoding). Only the service role may call it.
- Organizations that answered the GCC survey themselves (source `GCC survey`, or `verification_source` starting with `GCC survey`) are `updated_via = 'admin'` rows, so the pipeline keeps their answers; enrichment skips Jev for them. (They used to be re-added each run from `Data/Survey/survey-organizations.csv` and the `survey_verifications` table, both removed on 2026-11-24.)
- `pipeline_cache` and `api_log` have no policies: only the service role can use them.

## Planned logical entities (longer term)

## Planned logical entities

- `organizations`: canonical organization identity and publication state.
- `organization_names`: canonical and alternate names.
- `locations`: normalized addresses and coordinates with precision.
- `contacts`: people and communication channels with visibility rules.
- `source_records`: immutable records imported from each source.
- `source_observations`: field-level claims and provenance.
- `external_identifiers`: EIN and future source-specific IDs.
- `classifications`: GCC and source taxonomies.
- `organization_classifications`: many-to-many assigned categories.
- `verification_submissions`: organization-provided changes and review state.
- `change_history`: auditable canonical record changes.

Physical types, indexes, constraints, and database technology are TBD.

The prototype location properties also include `geocoding_provider`, `geocoding_status`, `geocoding_match_type`, `geocoded_address`, `geocoded_at`, and `location_precision`.

The prototype classification properties include raw `irs_category` plus dedicated `gcc_*` values for all eight product filters, along with alignment method, confidence, resolved source-category code, and crosswalk-version fields. Future canonical classification tables should retain this source-versus-aligned distinction and represent the source-category-to-target-category mapping as auditable provenance rather than an implicit transformation.
