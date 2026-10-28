# Tech Stack

## Initial stack

- Python 3 standard library for IRS ingestion and normalization.
- GeoJSON for the first map-facing data artifact.
- Static HTML, CSS, and JavaScript for the frontend.
- MapLibre GL JS for map rendering and client-side marker clustering.
- OpenStreetMap raster tiles for prototype basemap rendering.
- Python `http.server` for local development.
- Python `unittest` for ingestion tests.

## Rationale

The first slice has no package-install or build-step requirement. This reduces setup cost while the data contract and product interaction are still being validated. A production backend, database, geocoder, tile provider, and deployment platform remain TBD.

