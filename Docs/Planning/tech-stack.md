# Tech Stack

## Current stack

- Python 3 standard library for IRS ingestion, normalization, website discovery, and contact extraction.
- GeoJSON for the map-facing data artifact.
- Static HTML, CSS, and JavaScript for the frontend.
- MapLibre GL JS for map rendering and client-side marker clustering.
- OpenStreetMap raster tiles for prototype basemap rendering.
- Python `http.server` for local development.
- Python `unittest` for ingestion and enrichment tests.
- GitHub Actions for CI/CD deployment.
- GitHub Pages for static hosting (public site from a private repository).
- Brave Search API for primary website discovery.
- OpenAI Responses API (web search) for fallback website discovery when Brave returns no confident match.
- OpenRouter Decisions API with `typesafe/jev-1.13` for structured eight-field schema classification.

## Rationale

The build and enrichment paths have no package-install requirements beyond Python 3.10+. Brave Search is the cost-effective primary discovery path; OpenAI is reserved for ambiguous cases only. Jev handles all classification in a single structured API call so the search model never assigns filter values. GitHub Actions deploys the `app/` directory automatically on every push to `main` or `master`. A production backend, database, geocoder, tile provider, and deployment platform remain TBD.

