# GCC Climate Organization Map

## Project idea

The GCC Climate Organization Map is envisioned as a free, nationwide directory and interactive map of local climate and environmental organizations. Its distinguishing purpose is to make hyper-local organizations and community-level chapters discoverable, rather than concentrating only on large regional or national organizations.

The project is currently in the research and data-foundation stage. This workspace contains product requirements, data-source research, a preliminary target schema, selected environmental classification codes, and nationwide IRS source data. It does not yet contain an application, database, map implementation, or production ingestion pipeline.

For the initial map build, the IRS files in `Data/` will be the sole placeholder dataset. Additional sources and enrichment will be added later and combined through a source-agnostic ingestion and canonical-record layer. The first implementation should therefore prioritize getting the map working with normalized IRS records without embedding IRS-specific assumptions into the public map interface.

## Product purpose

The map is intended to help three primary audiences:

1. **Residents** who want to find nearby organizations and opportunities to participate locally. Other applications, such as MOVIEMENT, may direct users to the map.
2. **Funders** who want to understand where local climate resources exist, where gaps remain, and where funding could have the greatest effect.
3. **Organizations** that want to identify potential collaborators, whether nearby or in other regions.

The service will be published for free on the GCC website. Some collected information will be retained internally and will not appear publicly on the map.

## Intended user experience

Users should be able to explore the directory through standard interactive-map behavior:

- Pan, zoom, and rotate the map.
- Search by ZIP code, town or city, state, organization name, or address.
- Filter organizations by defined attributes.
- Select a map marker to open an organization profile card.
- Review a list of organizations matching the current map, search, and filter state.
- Follow a link from the profile card to verify or update an organization's information.

The requirements currently identify the following filters:

- Organization Type
- Audience Focus
- Resilience
- Activity
- Action Category
- Climate Categories
- Reach
- Verification

Map performance is a critical requirement. After all states have been populated, panning and zooming must remain responsive. Mapbox is mentioned as a possible platform, but it has not been formally selected.

## Organization profile content

The current target schema contains 24 fields:

| Area | Fields |
| --- | --- |
| Identity and contact | Name, Website URL, Source URL, Email, Phone |
| Location | Address, City, State, Postal Code, Latitude, Longitude |
| Classification | Action Category, Climate Categories, Organization Type, Reach |
| Content and workflow | Status, Summary, Tags, Social Links, Validated, Notes |
| Additional analysis | Advocacy vs Action, Audience Focus, Adaptation vs Mitigation |

The preliminary controlled values include the following.

### Action category

- Community Engagement
- Conservation
- Advocacy/Policy
- Other

### Climate categories

- Environmental: pollinators, native plants, clean air, and clean water
- Waste Reduction: reuse, repair, repurpose, recycle, and refuse
- Green Economics: buying local, supporting sustainable businesses, and green investing
- Food and Food Waste: composting, food choices, and local farming
- Transportation: public options and electric vehicles
- Energy Efficiency: heating and cooling, weatherization, and solar

### Organization type

- Nonprofit / Grassroots
- Coalition
- Municipality
- Business
- Academic
- Tribal/Indigenous
- Committee
- Unknown

### Reach

- Town / City
- Regional
- State / National
- Unknown

### Advocacy versus action

- Advocacy
- Action
- Both
- Unknown

### Audience focus

- Residents
- Municipality
- Businesses
- Residents / Municipality
- Residents / Businesses
- Municipality / Businesses
- Residents / Municipality / Businesses
- Unknown

### Adaptation versus mitigation

- Adaptation
- Mitigation
- Both
- Unknown

## Two-stage data lifecycle

### Phase I: Internet scan and discovery

Phase I populates the map with organizations found through structured datasets and internet searches. The desired information includes:

- Organization name
- Address
- Website
- Contact email and phone, ideally for the Executive Director
- Organization summary
- All applicable filter classifications

These records are unverified and should retain their source evidence. Automated imports must never overwrite an organization that has already been verified.

### Phase II: Organization verification

Phase II allows someone associated with an organization to complete a verification form linked from the organization's profile card.

Once a submission has been accepted, the new information replaces or supersedes the unverified Phase I information. The system must also support submissions for organizations that did not previously have a Phase I record.

This lifecycle implies that the database must preserve source provenance, verification state, and controlled merge rules. A simple overwrite-by-name import would not satisfy the requirements.

## Existing source data

The `Data/` directory contains 51 IRS Exempt Organizations Business Master File CSVs: all 50 states plus Washington, D.C.

An analysis of the supplied files found:

- **51 source files**
- **1,960,014 total IRS organization records**
- **28,633 records with any C-prefixed environmental NTEE code**
- **20,577 records matching the 17 specifically selected NTEE codes**
- **One consistent 28-column IRS schema across every file**

The IRS fields are:

`EIN`, `NAME`, `ICO`, `STREET`, `CITY`, `STATE`, `ZIP`, `GROUP`, `SUBSECTION`, `AFFILIATION`, `CLASSIFICATION`, `RULING`, `DEDUCTIBILITY`, `FOUNDATION`, `ACTIVITY`, `ORGANIZATION`, `STATUS`, `TAX_PERIOD`, `ASSET_CD`, `INCOME_CD`, `FILING_REQ_CD`, `PF_FILING_REQ_CD`, `ACCT_PD`, `ASSET_AMT`, `INCOME_AMT`, `REVENUE_AMT`, `NTEE_CD`, and `SORT_NAME`.

The 17 selected NTEE codes are:

- `C00`
- `C01`
- `C03`
- `C05`
- `C12`
- `C19`
- `C20`
- `C27`
- `C30`
- `C32`
- `C34`
- `C35`
- `C36`
- `C40`
- `C50`
- `C60`
- `C99`

These cover broad environmental work as well as pollution control, recycling, natural resources, water and wetlands, land, energy, forests, and environmental education.

The IRS records form a strong nationwide base layer, but they are not map-ready profiles. They generally do not provide websites, public email addresses, phone numbers, coordinates, summaries, social links, GCC classifications, or verification information. The 20,577 selected records should therefore be treated as candidates for enrichment and review rather than immediately published organizations.

## Initial placeholder map scope

The first working version of the map will use only the supplied IRS data. Its purpose is to validate the ingestion, geospatial, search, filtering, and map-display foundations before introducing multi-source complexity.

The initial pipeline should:

1. Read all state-level IRS CSV files from `Data/`.
2. Keep records whose `NTEE_CD` matches the selected codes in `Docs/NTEE_Codes_to_Consider.txt`.
3. Normalize EIN, organization name, address, city, state, and ZIP code.
4. Preserve the complete original IRS row or retain a traceable reference to it.
5. Assign a stable internal organization ID while retaining EIN as the IRS source identifier.
6. Geocode usable street addresses to obtain latitude and longitude for the map.
7. Record geocoding status, provider, confidence or precision, and timestamp.
8. Exclude or separately list records that cannot be mapped reliably.
9. Produce a map-facing dataset or database table with only the fields needed by the initial interface.
10. Display IRS-derived records as unverified placeholder profiles.

The initial map can support:

- Nationwide markers with clustering or another scalable rendering strategy.
- Search by organization name, city, state, ZIP code, and address.
- Filters based on currently available IRS values, especially NTEE code and geography.
- A basic profile card containing organization name, address, EIN, NTEE code, and IRS status where appropriate.
- A visible unverified or IRS-sourced label so users understand the data's current limitations.

Fields unavailable from the IRS—such as website, email, phone, summary, GCC climate categories, audience focus, social links, and verification details—should remain empty or explicitly marked unavailable. They should not be synthesized merely to make profiles appear complete.

### Preparing for later sources

Although the first map uses only IRS data, its internal model should separate the following concepts from the beginning:

- **Source record:** the original record received from IRS or a future source.
- **Canonical organization:** GCC's unified representation of a real organization.
- **Source observation:** a source's claim about a particular organization field.
- **Location:** one or more physical or service locations associated with an organization.
- **External identifier:** EIN for IRS records and equivalent IDs for future sources.
- **Verification state:** whether GCC or the organization has confirmed canonical information.

This boundary allows future ProPublica, OpenStreetMap, Climatebase, Exa, Meetup, verification-form, and other records to be imported without changing the map's public data contract. New records can be matched to canonical organizations using EIN where available and a scored combination of name, address, website, phone, and geographic proximity otherwise.

## Proposed data-source strategy

The research recommends a layered discovery and enrichment pipeline.

| Source | Type and cost | Primary purpose |
| --- | --- | --- |
| IRS EO BMF | Free bulk CSV download | Authoritative nationwide base dataset |
| ProPublica Nonprofit Explorer | Free REST API | Enrich IRS organizations and filing information |
| Climatebase | Web extraction, estimated small one-time cost | Discover curated climate-specific organizations |
| OpenStreetMap Overpass | Free geospatial API | Add precise locations and discover mapped NGOs |
| Exa | Paid semantic-search API | Find missing, new, or misclassified local groups |
| Meetup through Apify | Paid scraper | Find informal and unregistered grassroots groups |
| GlobalGiving Atlas | Paid API and bulk data | Optional registration-status validation and international expansion |

### IRS EO BMF

The IRS EO BMF is the recommended base dataset because it is authoritative, nationwide, free, and downloadable without pagination or API limits. It is updated monthly, reportedly on the second Tuesday of the month. The supplied repository data is already organized as state files.

The initial filter should use the selected environmental NTEE codes. Further rules may restrict records by subsection or status after the meaning and desired policy for those fields are confirmed.

### ProPublica Nonprofit Explorer

ProPublica can enrich organizations by EIN with nonprofit profile and filing data. The research proposes using it after the IRS filter rather than using it as the sole nationwide source. Search results are paginated, and the cited research recommends conservative request pacing.

### Exa semantic search

Exa is proposed for discovering organizations that are absent from or misclassified in IRS data, particularly in counties with low apparent coverage. County-level natural-language searches could target local climate, sustainability, and environmental groups. The research recommends limiting recurring searches to sparse counties to control cost.

### OpenStreetMap Overpass

Overpass can return geographic coordinates and community-contributed contact tags for objects such as NGOs, associations, and community centers. Its completeness varies significantly by region, and public endpoints should not be aggressively parallelized. A production-scale implementation may eventually need hosted or self-hosted capacity.

### Meetup through Apify

Meetup can surface local grassroots communities that do not have formal nonprofit status. Potential fields include group name, description, city, coordinates, member count, topics, organizer, group URL, and external links. It should be treated as a discovery source whose records still require normalization and verification.

### GlobalGiving Atlas

GlobalGiving Atlas may provide more current registration-status validation and broader coverage, but it requires a paid license. The research recommends deferring it unless GCC needs stronger registration validation or international expansion.

### Climatebase

Climatebase is proposed as a climate-focused discovery source containing companies and nonprofits. Its value is its climate relevance; its limitation is the lack of direct contact information. The research suggests web extraction and later website enrichment, subject to current terms, access rules, and technical validation.

## Proposed nationwide ingestion workflow

The proposed one-time nationwide build is:

1. Download and ingest all 51 IRS files.
2. Filter organizations using the selected environmental NTEE codes.
3. Normalize names, addresses, ZIP codes, EINs, and other source fields.
4. Enrich IRS candidates through ProPublica using EIN as the primary identity key.
5. Add climate-specific candidates from Climatebase.
6. Query OpenStreetMap for location-tagged organizations.
7. Measure geographic coverage and identify counties with fewer than a chosen number of candidates.
8. Use semantic search to discover organizations in sparse counties.
9. Search major cities for informal Meetup groups.
10. Merge and deduplicate candidates while retaining all source evidence.
11. Geocode records lacking reliable coordinates.
12. Classify organizations into GCC's controlled categories.
13. Route low-confidence or conflicting records for review.
14. Publish eligible unverified records without overwriting verified records.

## Proposed refresh strategy

The research proposes a roughly 15-day operational refresh for dynamic discovery sources:

1. Check monthly for a new IRS release and process it only when available.
2. Re-query sparse counties through semantic search.
3. Spot-check a limited set of major cities for new Meetup groups.
4. Optionally query OpenStreetMap for counties still identified as sparse.
5. Re-run normalization, deduplication, and change detection.
6. Protect all verified records from automated replacement.

The research estimates approximately **$5–10 per month** after the initial build. This estimate, along with all pricing, API limits, scraping methods, and terms of service, must be revalidated before implementation.

## Deduplication and identity

EIN is the most reliable deduplication key for registered organizations. Records with the same EIN should generally represent the same legal organization, although local chapters may require separate modeling.

For records without EINs, deduplication should consider multiple signals:

- Normalized organization name
- Street address and postal code
- Website domain
- Phone number and email domain
- Geographic proximity
- Parent organization and chapter relationship
- Source-specific identifiers

Fuzzy name matching can identify candidates for comparison, but it should not be the sole merge rule. Similar names can refer to unrelated organizations, and separate chapters may intentionally share a name.

Every merge should retain source lineage so that the origin and confidence of each field can be audited.

## Suggested system boundaries

The eventual product likely needs the following subsystems.

### 1. Ingestion and enrichment pipeline

Downloads, parses, normalizes, enriches, geocodes, classifies, and deduplicates source records. It should support repeatable runs, retries, source-specific rate limits, and change detection.

### 2. Canonical organization database

Stores organizations, locations, contacts, classifications, source evidence, external identifiers, verification history, and publication state. It should distinguish canonical values from individual source observations.

### 3. Verification workflow

Provides a public form, matches submissions to existing records, supports new organizations, protects verified information, and records who or what changed each value. It should include a process for ambiguous or conflicting claims.

### 4. Public map application

Provides geospatial browsing, search, filters, marker clustering, synchronized results, and organization profile cards. It should be responsive, mobile-friendly, accessible, and performant at nationwide scale.

### 5. CRM integration

Exports both Phase I and Phase II organizations and their permitted contact information to Zoho or another CRM. These records are expected to support email marketing, so consent, lawful-use, suppression, and public-versus-internal data rules must be explicit.

### 6. Reporting and administration

An internal dashboard is desirable for:

- Phase I organization counts by state and filter.
- Phase II organization counts by state and filter.
- Growth in both phases over time.
- Coverage gaps by geography.
- Verification throughput and backlog.
- Source performance and data-quality metrics.
- Additional Phase II dashboards referenced by the requirements.

## Core implementation principles

- Never overwrite verified information through an automated import.
- Preserve source URL, source identifier, retrieval time, and field-level provenance.
- Separate public organization information from internal contact and operational data.
- Use controlled vocabularies for filterable classifications.
- Treat automated classifications and summaries as confidence-scored suggestions until validated.
- Make ingestion idempotent so rerunning a source does not create duplicates.
- Maintain history instead of destroying superseded observations.
- Optimize public queries independently from raw ingestion storage.
- Design for local chapters and parent organizations explicitly.
- Monitor geographic and demographic coverage so dataset size is not mistaken for completeness.

## Unresolved decisions and gaps

The following items need explicit decisions before or during implementation:

1. **Technology stack:** frontend, backend, database, hosting platform, job runner, and deployment process are unspecified.
2. **Mapping platform:** Mapbox is mentioned but not selected.
3. **CRM:** Zoho versus another system remains undecided.
4. **Schema mismatch:** the requirements mention Resilience and Activity filters, but the target schema does not define corresponding fields clearly.
5. **Workflow semantics:** `Validated` and `Status` both exist, but their meanings and allowed values are undefined.
6. **Missing EIN:** the target schema lacks an EIN field even though EIN is the strongest identity and deduplication key.
7. **Missing contact structure:** the requirements prefer Executive Director information, but the schema has no contact name, role, consent, visibility, or provenance fields.
8. **Missing provenance:** source record ID, source name, retrieval date, last checked date, and per-field confidence are absent.
9. **Definition of local:** there is no formal test for hyper-local organizations or rules for national organizations with local chapters.
10. **Verification security:** claimant authentication, approval, dispute resolution, and conflicting submissions are unspecified.
11. **Privacy:** the project needs a formal policy identifying which contact fields are public, internal, or permitted for marketing use.
12. **Geocoding:** provider, cost, accuracy threshold, address normalization, P.O. box handling, and organizations without public locations are undecided.
13. **Publication eligibility:** there are no minimum completeness or confidence rules for putting a Phase I candidate on the public map.
14. **Data quality:** acceptance thresholds for duplicate rate, geocoding accuracy, classification confidence, freshness, and false positives are undefined.
15. **Performance:** no measurable targets exist for initial load, map movement, search latency, filtering, or maximum displayed markers.
16. **Accessibility and mobile:** no acceptance criteria have been written.
17. **Data-source compliance:** third-party prices, API behavior, licenses, scraping permissions, and terms need current verification.
18. **Reporting scope:** the Phase II dashboards referenced by the requirements are not fully described in the available files.

## Suggested next phase

The most practical next phase is to turn the current research into a narrow, testable data product before building the nationwide public interface:

1. Finalize a canonical schema with provenance, EIN, contacts, locations, verification, chapters, and publication state.
2. Define the controlled vocabularies and resolve the missing Resilience and Activity concepts.
3. Implement a repeatable IRS filtering and normalization pipeline.
4. Test enrichment, geocoding, classification, and deduplication on one representative state.
5. Manually review a sample to establish data-quality baselines.
6. Define verified-record protection and Phase II merge behavior.
7. Build a map prototype against the curated pilot dataset.
8. Measure search and map performance before scaling nationwide.
9. Add secondary discovery sources only after source compliance and value are validated.
10. Expand state by state while measuring coverage and false positives.

## Source material

- [`Climate Org Map Requirements.pdf`](../Research%20and%20Requirements/Climate%20Org%20Map%20Requirements.pdf)
- [`GCC_Data_Sources_Research.docx.pdf`](../Research%20and%20Requirements/GCC_Data_Sources_Research.docx.pdf)
- [`Schema - Sheet1.csv`](../Research%20and%20Requirements/Schema%20-%20Sheet1.csv)
- [`NTEE_Codes_to_Consider.txt`](../Research%20and%20Requirements/NTEE_Codes_to_Consider.txt)
- State-level IRS EO BMF CSV files in [`Data/`](../../Data/)

