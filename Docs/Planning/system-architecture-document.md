# System Architecture Document

## Current architecture

```text
IRS state CSV files
        |
        v
main.py orchestration
        |
        +--> Python ingestion and normalization
        |
        +--> Census match or state fallback assignment
        |
        +--> Brave Search / OpenRouter discovery + deterministic contact crawling
        |
        +--> Jev classification (OpenRouter Decisions API)
        |
        v
Generated GeoJSON (app/data/organizations.geojson)
        |
        v
GitHub Actions → GitHub Pages (auto-deploy on push)       scripts/sync_supabase.py
        |                                                         |
        v                                                         v
Static MapLibre web application (public URL)  <-- live changes --  Supabase `organizations`
                                                                  ^
add.html (visitor submissions, pending) ------------------------->|
admin.html (approve, verify, edit, delete, CSV; email sign-in) -->|
```

The static GeoJSON stays the map's snapshot (loading 20,000+ rows from the database on every visit would be slower). Supabase holds every organization and everything that changes after a pipeline run; the map merges the changed rows on load, so edits need no deploy.

## Future architecture boundary

Future sources should write source records and observations into a canonical organization layer. The public map should consume the canonical read model rather than depending directly on IRS field names.

```text
IRS / ProPublica / OSM / web discovery / verification forms
                         |
                         v
           source adapters and normalization
                         |
                         v
        matching, deduplication, and provenance
                         |
                         v
              canonical organization store
                         |
              +----------+----------+
              |                     |
              v                     v
          public map          admin / CRM / reports
```

## Production decisions

Backend, database, job scheduler, geocoder, hosting, authentication, and CRM integration are TBD.

