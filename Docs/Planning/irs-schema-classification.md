# IRS Schema Classification Rules

## Purpose

This document records how IRS EO BMF organizations receive provisional GCC schema categories during the initial dataset build.

The implementation is in `scripts/build_irs_dataset.py`. These classifications are deterministic placeholders. They use only the IRS NTEE code, organization name, and state abbreviation. They do not use an official website, mission statement, Form 990 program description, generative model, or Jev during the initial build.

After enrichment, Jev may replace the provisional values using evidence collected from official websites or Form 990 filings. The original IRS category and mapping provenance must remain available for audit.

## Record selection

Only organizations whose exact `NTEE_CD` appears in `Docs/Research and Requirements/NTEE_Codes_to_Consider.txt` are included.

The selected codes are:

- `C00` — Environment (General)
- `C01` — Alliance/Advocacy Organizations
- `C03` — Professional Societies and Associations
- `C05` — Research Institutes and Public Policy Analysis
- `C12` — Fund Raising and/or Fund Distribution
- `C19` — Support N.E.C.
- `C20` — Pollution Abatement and Control
- `C27` — Recycling
- `C30` — Natural Resources Conservation and Protection
- `C32` — Water Resource and Wetlands Conservation
- `C34` — Land Resources Conservation
- `C35` — Energy Resources Conservation and Development
- `C36` — Forest Conservation
- `C40` — Botanical, Horticultural, and Landscape Services
- `C50` — Environmental Beautification and Open Spaces
- `C60` — Environmental Education and Outdoor Survival Programs
- `C99` — Environment N.E.C.

## Climate category

Organization-name keywords take priority over the NTEE crosswalk. The first matching keyword group wins.

| Organization-name keywords | GCC category |
|---|---|
| food waste, compost, community garden, farm, farming, agriculture | Food & Food Waste |
| transit, transportation, bicycle, cycling, pedestrian, mobility, electric vehicle | Transportation |
| green business, sustainable business, local economy, green investment, green investing | Green Economics |
| solar, renewable energy, clean energy, energy efficiency, weatherization, electrification | Energy Efficiency |
| recycling, recycle, reuse, repair cafe, zero waste, waste reduction | Waste Reduction |

If no name keyword matches, NTEE determines the category:

| NTEE code | GCC category |
|---|---|
| `C27` | Waste Reduction |
| `C35` | Energy Efficiency |
| `C30`, `C32`, `C34`, `C36`, `C40`, `C50` | Conservation |
| Any other selected code | Environmental |

## Action category

| NTEE code | GCC action category |
|---|---|
| `C20`, `C27`, `C30`, `C32`, `C34`, `C35`, `C36`, `C40`, `C50` | Conservation |
| `C01` | Advocacy/Policy |
| `C60` | Community Engagement |
| Any other selected code | Other |

## Activity

Activity is derived from the provisional action category:

| Action category | Activity |
|---|---|
| Advocacy/Policy | Advocacy |
| Community Engagement | Action |
| Conservation | Action |
| Other | Unknown |

## Resilience

Resilience is derived from the provisional climate category:

| Climate category | Resilience |
|---|---|
| Conservation | Adaptation |
| Energy Efficiency | Mitigation |
| Green Economics | Mitigation |
| Transportation | Mitigation |
| Waste Reduction | Mitigation |
| Any other category | Both |

## Organization type

Organization type is inferred from the organization name in the following order:

| Organization-name indicators | Organization type | Confidence |
|---|---|---|
| university, college, academic, school of | Academic | Medium |
| city of, town of, village of, municipality of | Municipality | Medium |
| authority, commission, public district, government council | Municipal / Government-affiliated | Medium |
| coalition, alliance, network | Coalition | Medium |
| chamber of commerce, business council, business association | Business | Medium |
| No matching indicator | Nonprofit / Grassroots | High |

## Audience focus

Audience is inferred from organization type and organization-name indicators:

| Condition | Audience | Confidence |
|---|---|---|
| Organization type is Business | Businesses | Medium |
| Organization type is Municipality or Municipal / Government-affiliated | Municipality | Medium |
| Name contains community, citizen, resident, neighborhood, friends of, or public education | Residents | Medium |
| No matching evidence | Unknown | Low |

## Reach

Reach is inferred from organization type, organization name, and the IRS state:

| Condition | Reach | Confidence |
|---|---|---|
| Organization type is Municipality | Municipality | Medium |
| Name contains global, international, worldwide, or world | Global | Medium |
| Name contains national, American, United States, USA, or the full IRS state name | State / National | Medium |
| Name contains regional, region, county, or multi-county | Regional | Medium |
| Name contains community, neighborhood, local, or friends of | Town / City | Medium |
| No matching evidence | Unknown | Low |

## Verification

Every IRS organization begins as `Not Verified`, with `validated=false`.

Neither presence in the IRS data nor discovery of an official website constitutes GCC verification. Verification requires the separate GCC claim-and-verification process.

## Stored provenance

The source classification remains separate from the provisional GCC classification.

- `ntee_code`: untouched IRS NTEE code.
- `ntee_label`: human-readable NTEE label.
- `irs_category`: combined NTEE code and label.
- `gcc_alignment_method`: `NTEE crosswalk` or `organization name keyword + NTEE crosswalk`.
- `gcc_alignment_confidence`: confidence in the climate/action crosswalk.
- `gcc_organization_type_confidence`: organization-type rule confidence.
- `gcc_audience_focus_confidence`: audience rule confidence.
- `gcc_reach_confidence`: reach rule confidence.

The corresponding provisional public values are stored in:

- `gcc_organization_type`
- `gcc_audience_focus`
- `gcc_resilience`
- `gcc_activity`
- `gcc_action_category`
- `gcc_climate_category`
- `gcc_reach`
- `gcc_verification`

## Known limitation: single-value categories

Every category currently stores exactly one value. The current map schema and Jev request use one `choice` per field.

Examples such as an audience of `Businesses, Municipality, Residents` require a future schema decision: either support arrays and multi-select filtering or define separate yes/no decisions for each possible category. This behavior must not be introduced implicitly because it changes the public data contract and filter semantics.

## Relationship to Jev enrichment

The deterministic rules provide an immediately usable map and a fallback when enrichment is unavailable. They are not supplied as authoritative answers to Jev.

The enrichment pipeline:

1. Finds an official website or obtains other organization evidence.
2. Produces a source-grounded summary and evidence package.
3. Sends the evidence to Jev through OpenRouter.
4. Requests all eight controlled schema decisions in one call.
5. Stores Jev choices, probabilities, confidence values, model version, provider, request ID, and question version.
6. Preserves the original IRS and deterministic provenance for comparison and audit.
