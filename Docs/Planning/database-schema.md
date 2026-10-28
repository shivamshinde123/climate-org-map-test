# Database Schema

## Current release

The first slice uses generated GeoJSON and has no application database.

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
