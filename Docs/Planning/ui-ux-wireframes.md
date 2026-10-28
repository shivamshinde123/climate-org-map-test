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

## States

- Loading: visible status with no empty-map ambiguity.
- Ready: counts, filters, clustered map, and results.
- No matches: explanatory empty state and reset option.
- Data error: actionable message explaining how to generate or serve the dataset.
- Selected organization: focused point and compact profile popup.

