# IRS EO BMF, ProPublica, and map-category crosswalk

Last reviewed: 2026-10-07

## Result

ProPublica Nonprofit Explorer is useful as a filing and evidence source, but it
is **not an independent category system**. Its organization profile is built
from IRS EO BMF data and exposes the same central identifiers and tax
classifications, especially EIN, NTEE code, and IRC subsection. Consequently,
matching an IRS NTEE code to the ProPublica NTEE code confirms that the join and
source versions agree; it does not independently prove one of the map's product
categories.

The correct role of each source is:

```text
IRS EO BMF                 ProPublica Nonprofit Explorer       Target map schema
identity + tax codes  ---> EIN-joined BMF profile              product categories
        |                  + Form 990 filing data        --->  assigned from evidence
        |                                                        + provenance/confidence
        +------------------- baseline comparison ----------------+
```

## Source-field crosswalk

| IRS EO BMF | ProPublica API | Relationship | Use for target schema |
|---|---|---|---|
| `EIN` | `organization.ein` / `strein` | Same identifier; primary join key | Identity only |
| `NAME` | `organization.name` | Same organization profile, possibly from different BMF snapshots | Evidence for name-based fallback rules; not a category |
| `STREET`, `CITY`, `STATE`, `ZIP` | organization address fields | Headquarters/mailing address | Map location; does not establish geographic reach |
| `NTEE_CD` | `raw_ntee_code`, `ntee_code` | IRS NTEE classification republished by ProPublica | Candidate signal for Climate Category and sometimes Action Category |
| `SUBSECTION` | `subseccd` / subsection field | IRC exempt-organization subsection | Limited legal/tax signal for Organization Type |
| `AFFILIATION`, `CLASSIFICATION`, `FOUNDATION`, `ORGANIZATION` | corresponding organization-profile fields where present | IRS structural/tax metadata | Supporting evidence only; not direct product labels |
| `RULING`, `TAX_PERIOD`, `ASSET_AMT`, `INCOME_AMT`, `REVENUE_AMT` | profile and/or filing values | Timing and financial metadata | Not a requested filter category |
| No equivalent in EO BMF | `filings_with_data`, `filings_without_data`, form type, PDF URL and financial fields | ProPublica's primary added value | Filing availability and evidence; not ready-made target categories |

Field names vary slightly between the API's search and organization-detail
responses. The comparison script accepts the documented alternatives but never
silently treats one source's missing value as a match.

## Categories actually exposed by ProPublica

The API documentation exposes three categorical dimensions relevant to this
study:

1. `ntee[id]` on search is a ten-value **major-group filter**. Value 3 is
   Environment and Animals. It is only a search grouping, not one of the map's
   Climate Categories.
2. `ntee_code` (and `raw_ntee_code` in search results) is the detailed NTEE code,
   such as C30 or C34. ProPublica states that this comes from IRS BMF data.
3. `c_code[id]` / `subseccd` / `subsection_code` is the Internal Revenue Code
   exemption subsection, such as 3 for 501(c)(3). It describes tax status, not
   the organization's product type, audience, climate strategy, or reach.

Filing `formtype` is also categorical: 0 = Form 990, 1 = Form 990-EZ, and 2 =
Form 990-PF. It describes the return format and must not be used as a target map
category.

## Match to the requested map categories

### Organization Type

Requested values: Academic; Business; Coalition; Municipal / Government-affiliated;
Municipality; Nonprofit / Grassroots; Unknown.

- IRS contribution: subsection, affiliation, foundation, organization code,
  NTEE, and name are weak-to-moderate signals.
- ProPublica contribution: mostly the same BMF fields. A Form 990 narrative or
  schedule may add evidence, but the API does not return a target Organization
  Type category.
- Matching rule: do not map all 501(c)(3) records to Nonprofit / Grassroots.
  Legal tax status does not distinguish academic institutions, coalitions,
  municipalities, and grassroots groups.
- Safe result without adequate evidence: `Unknown`.

### Audience Focus

Requested values: Businesses; Municipality; Residents; Unknown.

- IRS contribution: none directly.
- ProPublica contribution: no audience category. Narrative program descriptions
  in underlying filings may provide evidence.
- Safe result without narrative evidence: `Unknown`.

### Resilience

Requested values: Adaptation; Both; Mitigation; Unknown.

- IRS contribution: an environmental NTEE code only establishes a broad domain.
- ProPublica contribution: no adaptation/mitigation category. Program or mission
  text may support classification.
- Safe result without explicit activity evidence: `Unknown`.

### Activity

Requested values: Action; Advocacy; Both; Unknown.

- IRS contribution: NTEE may weakly signal advocacy for a narrow subset of codes;
  names are not reliable enough by themselves.
- ProPublica contribution: filing narratives and lobbying-related filing fields
  may provide evidence. Financial/lobbying flags alone should not be generalized
  into all organizational activity.
- Safe result without evidence: `Unknown`.

### Action Category

Current project values: Community Engagement; Conservation; Advocacy/Policy;
Other; Unknown.

- IRS contribution: selected NTEE codes can be mapped as candidate signals.
- ProPublica contribution: its NTEE is the same IRS classification, not a second
  vote. Filing narratives can add independent textual evidence.
- Safe result when the NTEE is broad or ambiguous: `Unknown` (or `Other` only
  when evidence positively indicates an out-of-list action).

### Climate Category

Requested values: Conservation; Energy Efficiency; Environmental; Food & Food
Waste; Green Economics; Transportation; Waste Reduction; Unknown.

- IRS contribution: NTEE is the strongest structured candidate signal, although
  many NTEE codes are broader than these product categories.
- ProPublica contribution: `raw_ntee_code`/`ntee_code` repeats the IRS category.
  It can detect source-version disagreement but must not count as independent
  corroboration.
- Safe result for broad codes such as general environmental organizations:
  `Environmental` only if that broad mapping is an explicit product decision;
  otherwise `Unknown` pending narrative classification.

### Reach

Requested values: Global; Municipality; Regional; State / National; Town / City;
Unknown.

- IRS contribution: mailing address identifies a location, not service reach.
- ProPublica contribution: the same limitation applies. Filing text may mention
  a service area, but there is no reach category in the API.
- Safe result without explicit service-area evidence: `Unknown`.

## Explicit NTEE candidate mapping

The following is the conservative mapping encoded in
`Data/ProPublica/category-crosswalk.json`. The IRS and ProPublica columns are
identical by design because ProPublica obtains NTEE from the IRS BMF.

| IRS EO BMF NTEE | ProPublica category | Climate Category candidate | Action Category candidate | Activity candidate | Resilience candidate |
|---|---|---|---|---|---|
| C00 Environment, general | C00 / same label | Environmental | Unknown | Unknown | Unknown |
| C01 Alliance / Advocacy | C01 / same label | Environmental | Advocacy/Policy | Advocacy | Unknown |
| C03 Professional Societies / Associations | C03 / same label | Environmental | Unknown | Unknown | Unknown |
| C05 Research / Public Policy Analysis | C05 / same label | Environmental | Unknown | Unknown | Unknown |
| C12 Monetary Support - Multiple Organizations | C12 / same label | Environmental | Other | Unknown | Unknown |
| C19 Nonmonetary Support N.E.C. | C19 / same label | Environmental | Other | Unknown | Unknown |
| C20 Pollution Abatement and Control | C20 / same label | Environmental | Other | Action | Unknown |
| C27 Recycling | C27 / same label | Waste Reduction | Other | Action | Unknown |
| C30 Natural Resources Conservation | C30 / same label | Conservation | Conservation | Action | Unknown |
| C32 Water / Wetlands Conservation | C32 / same label | Conservation | Conservation | Action | Unknown |
| C34 Land Resources Conservation | C34 / same label | Conservation | Conservation | Action | Unknown |
| C35 Energy Resources Conservation | C35 / same label | Energy Efficiency | Conservation | Action | Mitigation |
| C36 Forest Conservation | C36 / same label | Conservation | Conservation | Action | Unknown |
| C40 Botanical / Horticultural / Landscape Services | C40 / same label | Conservation | Conservation | Action | Unknown |
| C50 Environmental Beautification | C50 / same label | Environmental | Other | Action | Unknown |
| C60 Environmental Education | C60 / same label | Environmental | Community Engagement | Action | Unknown |
| C99 Environment N.E.C. | C99 / same label | Environmental | Unknown | Unknown | Unknown |

This source selection provides no direct structured match for Food & Food Waste,
Green Economics, or Transportation. Those values should only come from richer
narrative evidence. `Both` should likewise never be inferred merely because two
weak keywords or broad codes are present.

## Recommended evidence model

Each assigned target category should retain:

- `value` — one allowed schema value;
- `source` — `irs_bmf`, `propublica_990`, `organization_website`, `jev`, or
  `human_review`;
- `evidence` — source field, excerpt reference, or filing URL;
- `confidence` — bounded score or Low/Medium/High;
- `classified_at` and classifier/model version.

This prevents the map from displaying inferred values as facts and makes a later
Jev classification reviewable.

## Reproducible comparison

1. `fetch_propublica_nonprofits.py` selects a deterministic stratified sample by
   IRS NTEE code and retrieves each organization by EIN.
2. Successful responses are cached in `Data/ProPublica/raw`; existing valid
   records are skipped on later runs.
3. `analyze_propublica_categories.py` joins the sources by EIN, measures exact
   NTEE/subsection agreement, inventories organization fields, and counts filing
   availability and form types.
4. The outputs are `irs-propublica-comparison.csv` and `analysis-summary.json`.

The comparison should be rerun whenever the input BMF snapshot or cached
ProPublica sample changes. A mismatch is a version/provenance issue to inspect,
not permission to choose whichever category is more convenient.

## Live spot check

Two EINs present in the project's IRS selection were checked in Nonprofit
Explorer on 2026-10-07:

| EIN | ProPublica organization | ProPublica/IRS category shown | Conservative target match |
|---|---|---|---|
| `20-2860877` | Alaska Farmland Trust Corporation | NTEE `C34`, Land Resources Conservation; 501(c)(3) | Climate Category = Conservation; Action Category = Conservation. Organization Type has nonprofit evidence, but no evidence that it is grassroots. Other target fields remain Unknown. |
| `20-3140552` | Friends of Campbell Tract | NTEE `C30`, Natural Resources Conservation and Protection; 501(c)(3) | Climate Category = Conservation; Action Category = Conservation. Other target fields require narrative or human evidence. |

Both pages add filing history and financial data, but their category labels are
the IRS NTEE and tax subsection. This observed behavior matches the API
documentation and supports the conclusion that ProPublica is an evidence source,
not a second category authority.

## Stratified API sample result

The executable sampler was run on 2026-10-07 for up to two organizations per
observed IRS NTEE code. Together with the two named spot checks, 34 cached
organizations were analyzed:

- 34/34 had NTEE in both sources; all 34 were exact matches.
- 34/34 had an exemption subsection in both sources; all 34 matched after
  normalizing equivalent representations such as `03` and `3`.
- Only 15/34 had structured filing data. Therefore, ProPublica filing evidence
  is useful but cannot be assumed to exist for every BMF organization.
- Across those filings, the sample contained 80 Form 990, 25 Form 990-EZ, and 2
  Form 990-PF records.

These figures describe this deterministic sample, not the full IRS dataset. The
machine-readable results are in `Data/ProPublica/analysis-summary.json` and
`Data/ProPublica/irs-propublica-comparison.csv`.

## API limitations and decisions

- The documented v2 endpoints use GET and do not require an API key.
- The API is described by ProPublica as a work in progress; response parsing is
  defensive and raw responses are retained for audit.
- Some organizations have no structured filing data, including organizations
  that only submit Form 990-N e-Postcards.
- Respectful delay, bounded retry, resumable caching, and a descriptive User-Agent
  are used even though the documentation does not publish a fixed rate limit.
- A full 20,000-record fetch should only follow validation of the small sample.

## Official references

- ProPublica Nonprofit Explorer API documentation:
  <https://projects.propublica.org/nonprofits/api/>
- ProPublica Nonprofit Explorer data explanation:
  <https://projects.propublica.org/nonprofits/about>
- IRS NTEE information:
  <https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf>
