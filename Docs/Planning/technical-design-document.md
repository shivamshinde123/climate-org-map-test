# Technical Design Document

## IRS ingestion

The build command recursively discovers `eo_*.csv` below `Data/`, filters exact NTEE codes, normalizes text, assigns a stable internal ID, and emits a GeoJSON feature with null geometry for each accepted record.

Category-level classification is resolved by `scripts/category_crosswalk.py` from the versioned `Data/ProPublica/category-crosswalk.json`. The same resolver is used by IRS ingestion, ProPublica comparison, and the generic external adapter. It recognizes an explicit NTEE code, a code embedded in a category label, or an exact punctuation-insensitive NTEE label. Unknown source labels produce only `Unknown` target values. Each result carries the resolved code, mapping basis, and crosswalk version so source-to-target edges remain auditable.

`geocode_organizations.py` owns all coordinate assignment. It applies cached or live U.S. Census address-range matches when available, then generates a deterministic state-level fallback for every remaining supported U.S. state record. Fallbacks are marked `state_level_fallback`; Census matches are marked `census_address_range`. The `--fallback-only` mode skips external requests while still producing a usable map.

## Frontend

The browser loads one GeoJSON file, applies client-side search and filters, and replaces the MapLibre source data with the filtered feature collection. MapLibre clusters points at lower zoom levels. A bounded result list avoids rendering thousands of DOM rows.

Popups intentionally expose only the organization name, address, the seven public classification values (Type, Audience, Resilience, Activity, Action, Climate, and Reach), an optional HTTP(S) website, an optional escaped summary, and the claim-and-verification link. IRS filing, financial, NTEE, alignment-confidence, and coordinate-precision fields remain in the dataset but are not shown in the popup.

Popup content is height-constrained to the visible viewport and scrolls independently. Wheel, touch, and pointer gestures inside a popup do not propagate to the map, so users can reach long organization details without changing map zoom or position.

Runtime schema and GeoJSON requests bypass the browser cache and carry a version query. Filter values are normalized and deduplicated case-insensitively in the browser as a final defense against mixed-version or stale artifacts.

## Future compatibility

Frontend code reads normalized property names, not raw IRS column names. Future source adapters can therefore emit the same map contract while the persistence layer evolves.
