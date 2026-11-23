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
Supabase (only data store)
  organizations         <-- add.html (visitor submissions, pending)
  pipeline_cache        <-- admin.html (approve, verify, edit, delete, CSV; email sign-in)
  api_log, survey_verifications
        |
        v  approved rows, map fields only (REST, anon key)
Static MapLibre web application (GitHub Pages, auto-deploy of app/ on push)
```

Supabase is the only data store. The pipeline loads organizations from it and saves new and changed records back (`scripts/supabase_store.py`); paid API answers, the API log and survey evidence are tables too. The map loads every approved organization on each visit, asking only for the fields its pins, list and filters use (about 1 MB compressed for 20,600 rows, 21 parallel requests of 1,000 rows) and fetching a popup's details when it opens. Edits are live immediately with no deploy. The only files in `app/data/` are fixed settings: filter vocabulary, survey questions, ZIP centroids and town lists.

Limit to watch: the Supabase Free plan includes about 5 GB of egress a month, roughly 5,000 map loads at ~1 MB each. Beyond that, upgrade to Pro (250 GB).

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

