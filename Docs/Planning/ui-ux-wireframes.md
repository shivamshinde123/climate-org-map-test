# UI/UX Wireframes

## Design direction

An editorial field-atlas aesthetic: warm paper tones, deep forest ink, survey-grid details, and a restrained safety-orange accent. The interface should feel civic and geographic rather than like a generic analytics dashboard.

The complete left panel scrolls vertically when its content exceeds the viewport. Filters expand naturally without a nested scrollbar. An always-visible edge control collapses or restores the panel, and the map resizes into the available space. The map does not display a separate marker legend; point and cluster behavior is communicated through interaction and counts.

## Desktop

```text
+---------------------------+--------------------------------------+
| GCC / CLIMATE FIELD ATLAS |                                      |
| Nationwide IRS preview    |                                      |
|                           |                                      |
| [ Search organizations ]  |             MAP                     |
| [ State ] [ NTEE code ]   |       clusters and points            |
| Organization filters (8) |                                      |
| [all visible by default]  |                                      |
|                           |                                      |
| 20,577 candidate records  |                                      |
| ------------------------- |                                      |
| Result                    |                                      |
| Result                    |                                      |
| Result                    |                                      |
|                           |                                      |
| Approximate location note |                                      |
+---------------------------+--------------------------------------+
```

## Mobile

```text
+--------------------------+
| Title and data notice    |
| Search and filters       |
|--------------------------|
|                          |
|           MAP            |
|                          |
|--------------------------|
| Matching results         |
+--------------------------+
```

## Add your organization (add.html)

Linked from the map header by a filled "+ Add your organization" button. At the top, a collapsed "How to add an organization" bar (Show rules / Hide rules) with the visitor rules, a column table with allowed values, and an example CSV. Then one card with the organization form (name, website, address, town, state, ZIP, filter selects; Verification is not offered), a second card for CSV upload with a downloadable template. Messages: submitted ("will appear once reviewed"), validation errors, per-row CSV problems.

## Verification survey (survey.html)

Opened from a listing's "Claim and verify this listing" (pre-filled, with a "You are verifying …" note) or directly. One section card at a time, styled like the site: questions in white boxes, required ones marked *, "This is a required question" under any left empty, radio and check-box lists with an "Other:" box, the state dropdown and town/address suggestions for the organization's location, Back and Next (Next becomes Submit on the last section of the chosen path). The intro shows a live example listing card. After submitting, the form's thank-you message.

## Admin (admin.html)

Not linked from the map. Sign-in card (email link) → a collapsed "How to add and edit organizations" rules bar at the top (admin rules, column table including verification, example CSV) → "Waiting for review" list (Approve / Edit / Delete), "Find an organization" search with Edit buttons and "add a new organization", the editor card (all fields plus Verification, latitude, longitude; Save, Find latitude & longitude (fills the coordinates from the address), Delete, Cancel), and an admin CSV upload that goes live immediately.

## States

- Loading: visible status with no empty-map ambiguity.
- Ready: counts, filters, clustered map, and results.
- No matches: explanatory empty state and reset option.
- Data error: actionable message explaining how to generate or serve the dataset.
- Selected organization: focused point and compact profile popup.

