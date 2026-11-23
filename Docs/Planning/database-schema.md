# Database Schema

## Current release

Organizations live in one Supabase (Postgres) table, created by `supabase/migrations/20261123000000_organizations.sql`. The generated GeoJSON stays as the map's fast-loading snapshot.

### `organizations`

| Column | Type | Notes |
|---|---|---|
| `id` | text, primary key | Same id as the map feature (`org_…` for IRS, `survey_…` for survey-only, `added_…` for form/CSV additions; `added_` ids hash name + state, so the same organization cannot be added twice). |
| `properties` | jsonb | Exactly the map feature's properties, so the pipeline, the map and the forms share one shape. |
| `review_status` | text | `pending` (visitor submission), `approved` (on the map), `removed` (deleted by the admin; kept only for pipeline rows), `rejected` (unused). |
| `updated_via` | text | Who last changed the row: `pipeline`, `admin`, `public_form`. |
| `created_at`, `updated_at` | timestamptz | `updated_at` is set by a trigger on every update. |
| `name`, `city`, `state`, `verification` | text, generated | Read-only copies of `properties` fields for admin search. |

Deleting: rows added through the forms are deleted outright. Pipeline rows are also in the static GeoJSON and would be re-sent by the next sync, so a deleted pipeline row stays as `removed` / `admin`: the map drops it and the sync leaves it alone.

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

### `admins`

`email` (primary key). Readable and writable only with the service role key. `scripts/sync_supabase.py` keeps it equal to `ADMIN_EMAILS` (adds and removes; an empty setting changes nothing).

### Access rules (row-level security)

- Anyone may read rows with `updated_via <> 'pipeline'` and `review_status` `approved` or `removed`; the map overlays these on the snapshot.
- Anyone may insert a row only if it is `pending`, `public_form`, `Not Verified`, and under 16 KB.
- An email in `admins` (checked by `is_admin()`) may read, change and delete every row.
- `sync_pipeline_organizations(rows jsonb)` upserts pipeline rows and never overwrites a row with `updated_via` other than `pipeline`. Only the service role may call it.

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
