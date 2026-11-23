# API Specification

## Current release

The map reads organizations from Supabase's REST API with the public anon key; row-level security returns only `approved` rows.

### Map dataset

`GET {SUPABASE_URL}/rest/v1/rpc/map_organizations`

Returns every organization the caller may read (`approved` only, through row-level security) as one JSON array. Each row is a compact array from the stored `map` column, in this order: `id`, `name`, `address`, `city`, `state`, `postal_code`, `source_id`, the eight `gcc_*` filter fields (`organization_type`, `audience_focus`, `resilience`, `activity`, `action_category`, `climate_category`, `reach`, `verification`), `latitude`, `longitude`. `MAP_FIELDS` in `app/app.js` must use the same order. A row with no numeric latitude/longitude has no map point. One request takes about 50 ms in the database; paging through the full `properties` took about 1 s per 1,000 rows and timed out when the map fetched pages in parallel.

`GET {SUPABASE_URL}/rest/v1/organizations?select=properties&id=eq.{id}` loads one organization's full record when its popup opens.

`properties` holds the complete normalized schema:

- `id`, `name`, `website_url`, `source_url`, `email`, and `phone`
- `address`, `city`, `state`, `postal_code`, `latitude`, and `longitude`
- `action_category`, `climate_categories`, `organization_type`, and `reach`
- `status`, `summary`, `tags`, `social_links`, `validated`, and `notes`
- `advocacy_vs_action`, `audience_focus`, and `adaptation_vs_mitigation`

IRS provenance and tooltip fields are also retained:

- `source`, `source_id`, `ntee_code`, and `ntee_label`
- `irs_category`, `gcc_climate_category`, and `gcc_action_category`
- `gcc_organization_type`, `gcc_audience_focus`, `gcc_resilience`, and `gcc_activity`
- `gcc_reach` and `gcc_verification`
- `gcc_alignment_method` and `gcc_alignment_confidence`
- `gcc_organization_type_confidence`, `gcc_audience_focus_confidence`, and `gcc_reach_confidence`
- `in_care_of`, `subsection`, `irs_status`, and `ruling_date`
- `tax_period`, `asset_amount`, `income_amount`, and `revenue_amount`
- `location_precision`

`website_url` stores the accepted official organization website as an HTTP(S) URL. `summary` stores the evidence-based plain-text organization description shown in the map popup. Empty values are permitted until enrichment succeeds; they must not be fabricated from insufficient evidence.

### Runtime schema

`GET /data/map-schema.json`

Returns the 24 normalized field names and the complete option vocabulary for Organization Type, Audience Focus, Resilience, Activity, Action Category, Climate Categories, Reach, and Verification. Options remain visible even when the current IRS dataset contains zero matching records.

## Future API

Search, organization detail, verification, administration, and CRM endpoints are TBD.

