# Product Requirements Document

## Product

GCC Climate Organization Map: a free nationwide map and directory of local climate and environmental organizations.

## Initial release goal

Build a working map from the IRS CSV files in `Data/`. The IRS data is a temporary base layer used to validate ingestion, search, filtering, clustering, and profile-card behavior.

## Users

- Residents seeking local groups.
- Funders assessing coverage and gaps.
- Organizations seeking collaborators.

## MVP requirements

- Ingest all supplied state IRS CSV files.
- Select records using `Docs/Research and Requirements/NTEE_Codes_to_Consider.txt`.
- Normalize records into a map-facing schema.
- Clearly label IRS records as unverified and distinguish Census address-range coordinates from approximate ZIP/city fallback coordinates.
- Search by name, address, city, state, and ZIP code.
- Filter by state and NTEE code.
- Provide the documented Organization Type, Audience Focus, Resilience, Activity, Action Category, Climate Categories, Reach, and Verification filters using the normalized schema.
- Cluster markers and keep interaction responsive.
- Show a tooltip for a selected organization using available IRS identity, address, classification, filing, and financial fields.
- Show the official website and an evidence-based organization summary in the tooltip when enrichment has populated them.
- Include a “Click to claim and verify” link in every tooltip that opens the GCC Google verification form.

## Out of scope for the first slice

- Organization-verified point locations.
- Organization verification submissions.
- CRM synchronization.
- Secondary data sources and cross-source merging.
- Authentication and administrative workflows.

## Acceptance criteria

- The build script processes all 51 files without third-party Python packages.
- Only configured NTEE codes appear in the output.
- The generated file identifies its source and coordinate precision.
- The site loads the generated dataset, renders clustered markers, and supports search and filters.
- No approximate coordinate is presented as a verified street location.

