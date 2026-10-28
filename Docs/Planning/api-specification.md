# API Specification

## Current release

There is no network application API in the initial static prototype.

### Map dataset

`GET /data/organizations.geojson`

Returns a GeoJSON `FeatureCollection`.

Each feature contains a Point geometry and the complete normalized map schema:

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

The collection includes a top-level `metadata` object describing generation time, selected codes, source files, and record count.

`website_url` stores the accepted official organization website as an HTTP(S) URL. `summary` stores the evidence-based plain-text organization description shown in the map popup. Empty values are permitted until enrichment succeeds; they must not be fabricated from insufficient evidence.

### Runtime schema

`GET /data/map-schema.json`

Returns the 24 normalized field names and the complete option vocabulary for Organization Type, Audience Focus, Resilience, Activity, Action Category, Climate Categories, Reach, and Verification. Options remain visible even when the current IRS dataset contains zero matching records.

## Future API

Search, organization detail, verification, administration, and CRM endpoints are TBD.

