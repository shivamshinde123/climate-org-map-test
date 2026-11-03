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
GitHub Actions → GitHub Pages (auto-deploy on push)
        |
        v
Static MapLibre web application (public URL)
```

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

