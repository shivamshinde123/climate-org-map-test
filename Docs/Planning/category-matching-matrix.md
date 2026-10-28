# Category Matching Matrix

Last updated: 2026-10-07  
Status: Proposed conservative mapping for review

## Purpose

This document shows the category relationship among:

1. the IRS Exempt Organizations Business Master File (EO BMF);
2. the ProPublica Nonprofit Explorer API; and
3. the Climate Org Mapping schema.

The mapping is deliberately conservative. A source value is mapped only when
its meaning supports the target value. Missing evidence becomes `Unknown`; it is
not filled using organization-name keywords or assumptions.

## Important source relationship

ProPublica is not a second, independent organization-category authority. Its
organization profile obtains fields such as NTEE code and tax subsection from
IRS EO BMF data.

| Category dimension | IRS EO BMF | ProPublica | Relationship |
|---|---|---|---|
| Organization identifier | `EIN` | `ein`, `strein` | Same identifier and join key |
| Detailed nonprofit category | `NTEE_CD` | `ntee_code`, `raw_ntee_code` | Same IRS NTEE classification |
| Broad nonprofit category | First character of `NTEE_CD` | Search `ntee[id]`; Environment and Animals is group 3 | ProPublica groups IRS NTEE codes for searching |
| Tax-exemption category | `SUBSECTION` | `subsection_code`, `subseccd`, search `c_code[id]` | Same Internal Revenue Code subsection |
| Filing category | Not supplied as a BMF organization category | `formtype`: 0 = 990, 1 = 990-EZ, 2 = 990-PF | Describes the filing, not the organization’s climate work |
| Filing evidence | Not present in EO BMF | Structured filing fields, PDF and sometimes XML | Additional ProPublica evidence; not a target category by itself |

Therefore, an IRS NTEE value and an identical ProPublica NTEE value count as one
classification lineage. They should not be treated as two votes for the same
target value.

## Your allowed target categories

| Target field | Allowed values |
|---|---|
| Organization Type | Academic; Business; Coalition; Municipal / Government-affiliated; Municipality; Nonprofit / Grassroots; Unknown |
| Audience Focus | Businesses; Municipality; Residents; Unknown |
| Resilience | Adaptation; Both; Mitigation; Unknown |
| Activity | Action; Advocacy; Both; Unknown |
| Action Category | Community Engagement; Conservation; Advocacy/Policy; Other; Unknown |
| Climate Categories | Conservation; Energy Efficiency; Environmental; Food & Food Waste; Green Economics; Transportation; Waste Reduction; Unknown |
| Reach | Global; Municipality; Regional; State / National; Town / City; Unknown |
| Verification | Not Verified; Verified |

Values that differ only by capitalization, such as `adaptation` and
`Adaptation`, should not be stored as separate categories. The canonical values
above should be used.

## Detailed IRS–ProPublica–target mapping

The IRS and ProPublica source-category columns are intentionally the same. The
ProPublica API is useful for detecting snapshot disagreement and locating filing
evidence, but its NTEE code originates from IRS data.

| IRS EO BMF category | ProPublica API category | Proposed Climate Category | Proposed Action Category | Proposed Activity | Proposed Resilience | Confidence and reason |
|---|---|---|---|---|---|---|
| C00 — Environment, general | C00 — same IRS NTEE | Environmental | Unknown | Unknown | Unknown | Medium for Environmental; the code is too broad for the remaining fields |
| C01 — Alliance / Advocacy Organizations | C01 — same IRS NTEE | Environmental | Advocacy/Policy | Advocacy | Unknown | High for advocacy; resilience strategy is not encoded |
| C03 — Professional Societies / Associations | C03 — same IRS NTEE | Environmental | Unknown | Unknown | Unknown | Medium for Environmental; association status does not describe its work |
| C05 — Research Institutes and/or Public Policy Analysis | C05 — same IRS NTEE | Environmental | Unknown | Unknown | Unknown | Medium for Environmental; research or policy analysis is not necessarily advocacy |
| C12 — Monetary Support, Multiple Organizations | C12 — same IRS NTEE | Environmental | Other | Unknown | Unknown | Medium; identifies funding/support rather than program activity |
| C19 — Nonmonetary Support N.E.C. | C19 — same IRS NTEE | Environmental | Other | Unknown | Unknown | Medium; identifies support activity but gives little program detail |
| C20 — Pollution Abatement and Control | C20 — same IRS NTEE | Environmental | Other | Action | Unknown | High for direct environmental action; pollution work is broader than climate resilience |
| C27 — Recycling | C27 — same IRS NTEE | Waste Reduction | Other | Action | Unknown | High for Waste Reduction and Action |
| C30 — Natural Resources Conservation and Protection | C30 — same IRS NTEE | Conservation | Conservation | Action | Unknown | High for Conservation and Action |
| C32 — Water Resources / Wetlands Conservation and Management | C32 — same IRS NTEE | Conservation | Conservation | Action | Unknown | High for Conservation; adaptation cannot be assumed without climate evidence |
| C34 — Land Resources Conservation | C34 — same IRS NTEE | Conservation | Conservation | Action | Unknown | High for Conservation and Action |
| C35 — Energy Resources Conservation and Development | C35 — same IRS NTEE | Energy Efficiency | Conservation | Action | Mitigation | High for energy and action; Medium for Mitigation because energy conservation normally reduces emissions |
| C36 — Forest Conservation | C36 — same IRS NTEE | Conservation | Conservation | Action | Unknown | High for Conservation; forest work may have mitigation or adaptation benefits, but neither is guaranteed |
| C40 — Botanical, Horticultural and Landscape Services | C40 — same IRS NTEE | Conservation | Conservation | Action | Unknown | Medium; some organizations may focus on horticultural services rather than conservation |
| C50 — Environmental Beautification and Aesthetics | C50 — same IRS NTEE | Environmental | Other | Action | Unknown | Medium; the target schema has no beautification category |
| C60 — Environmental Education and Outdoor Survival Programs | C60 — same IRS NTEE | Environmental | Community Engagement | Action | Unknown | Medium; education supports engagement, but the audience and climate strategy are not encoded |
| C99 — Environment N.E.C. | C99 — same IRS NTEE | Environmental | Unknown | Unknown | Unknown | Medium for Environmental; all more-specific classifications require additional evidence |

## Target values not supported by the selected NTEE codes

The selected IRS records do not contain a detailed NTEE code that directly and
reliably produces these Climate Categories:

- Food & Food Waste
- Green Economics
- Transportation

These values require organization website text, Form 990 mission/program text,
another external data source, Jev classification, or human review.

## Field-by-field proposed rules

### Organization Type

| Source evidence | Proposed target result |
|---|---|
| IRS/ProPublica subsection is 501(c)(3) | Do not automatically choose Nonprofit / Grassroots; universities, foundations, coalitions, and other institution types may also be 501(c)(3) |
| NTEE is C03 | Possible association evidence, but not enough to prove Coalition |
| Organization or filing evidence explicitly identifies a college or university | Academic |
| Explicit business or commercial entity evidence | Business |
| Explicit alliance, network, or coalition evidence | Coalition |
| Explicit government affiliation but not the municipality itself | Municipal / Government-affiliated |
| Explicit municipal government entity | Municipality |
| Explicit nonprofit or grassroots identity after excluding more-specific types | Nonprofit / Grassroots |
| Evidence is insufficient or conflicting | Unknown |

Proposed structured-source default: `Unknown`.

### Audience Focus

Neither IRS NTEE nor the ProPublica organization profile identifies whether an
organization serves Businesses, Municipality, or Residents. Filing narratives
or website content must explicitly establish the audience.

Proposed structured-source default: `Unknown`.

### Resilience

| Source evidence | Proposed result |
|---|---|
| NTEE C35 energy conservation | Mitigation candidate |
| Explicit emissions-reduction, decarbonization, renewable-energy, or efficiency evidence | Mitigation |
| Explicit preparedness, flood protection, heat resilience, climate-risk reduction, or adaptation evidence | Adaptation |
| Strong explicit evidence of both | Both |
| General conservation/environmental classification only | Unknown |

### Activity

| Source evidence | Proposed result |
|---|---|
| NTEE C01 | Advocacy |
| Direct-service NTEE C20, C27, C30, C32, C34, C35, C36, C40, C50, or C60 | Action candidate |
| Strong explicit evidence of program implementation and advocacy | Both |
| Research, professional association, funding, general, or N.E.C. code alone | Unknown |

### Action Category

| Source evidence | Proposed result |
|---|---|
| NTEE C01 | Advocacy/Policy |
| NTEE C30, C32, C34, C35, C36, or C40 | Conservation |
| NTEE C60 | Community Engagement candidate |
| NTEE C12, C19, C20, C27, or C50 | Other |
| NTEE C00, C03, C05, or C99 | Unknown |

`Other` should mean that positive evidence identifies an activity outside the
named options. It should not be used merely because evidence is missing.

### Climate Categories

| Source evidence | Proposed result |
|---|---|
| NTEE C27 | Waste Reduction |
| NTEE C30, C32, C34, C36, or C40 | Conservation |
| NTEE C35 | Energy Efficiency |
| NTEE C00, C01, C03, C05, C12, C19, C20, C50, C60, or C99 | Environmental |
| Explicit food-system or food-waste evidence | Food & Food Waste |
| Explicit green-finance, green-jobs, or sustainable-economic-development evidence | Green Economics |
| Explicit transit, active-transportation, electric-vehicle, or mobility evidence | Transportation |
| No adequate evidence | Unknown |

### Reach

The IRS/ProPublica street, city, and state fields represent the organization's
mailing or headquarters location. They do not establish where the organization
works.

| Evidence | Proposed result |
|---|---|
| Explicitly operates worldwide | Global |
| Serves one municipal government | Municipality |
| Explicit multi-city or multi-county region | Regional |
| Explicit statewide or nationwide operation | State / National |
| Explicitly serves one town or city | Town / City |
| Address only or no service-area evidence | Unknown |

### Verification

| Evidence | Proposed result |
|---|---|
| Imported from IRS or found in ProPublica | Not Verified |
| Completed Climate Org Mapping claim-and-verification workflow | Verified |

IRS or ProPublica presence proves that a public tax record exists. It does not
mean the organization has verified its map listing.

## Empirical ProPublica comparison

A deterministic sample of 34 organizations was fetched from ProPublica, covering
up to two records per observed IRS NTEE code plus two named spot checks.

| Check | Result |
|---|---:|
| NTEE present in both sources | 34/34 |
| Exact NTEE matches | 34/34 |
| Subsection present in both sources | 34/34 |
| Exact subsection matches | 34/34 |
| Organizations with structured filing data | 15/34 |
| Organizations without structured filing data | 19/34 |

The complete machine-readable mapping is in
`Data/ProPublica/category-crosswalk.json`. The observed comparison is in
`Data/ProPublica/irs-propublica-comparison.csv`, and aggregate statistics are in
`Data/ProPublica/analysis-summary.json`.

## Recommended implementation policy

1. Join IRS and ProPublica using normalized nine-digit EIN.
2. Preserve the original IRS and ProPublica values separately.
3. Record whether their NTEE/subsection values agree.
4. Apply the candidate mapping above only to supported fields.
5. Leave unsupported values as `Unknown`.
6. Use Form 990 narrative, website evidence, Jev, or human review for the
   remaining schema fields.
7. Store the evidence source, confidence, classifier version, and classification
   time with every inferred value.

## References

- ProPublica Nonprofit Explorer API: <https://projects.propublica.org/nonprofits/api/>
- IRS EO BMF information: <https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf>
- NCCS NTEE code documentation: <https://nccs.urban.org/project/national-taxonomy-exempt-entities-ntee-codes>
