# File and Folder Structure

```text
Climate Org Mapping/
|-- .env                              # local secrets; ignored
|-- .env.example                      # safe configuration template
|-- .gitignore
|-- main.py                           # complete build, geocode, validate, and serve entry point
|-- .github/
|   `-- workflows/
|       |-- deploy.yml                # on push to master: supabase db push, then deploy app/ to GitHub Pages
|       `-- keep-awake.yml            # every 3 days: one read so the free Supabase project never pauses
|-- app/
|   |-- data/
|   |   |-- map-schema.json           # filter and field vocabulary
|   |   |-- survey.json               # every survey section, question, option and branch
|   |   |-- zip-centroids.json        # ZIP -> [lat, lng] fallback for the forms (from Data/Geocoding)
|   |   `-- towns/<STATE>.json        # town suggestions per state (scripts/build_town_lists.py)
|   |-- app.js                        # map; loads approved organizations from Supabase
|   |-- index.html
|   |-- add.html                      # public "Add your organization" form and CSV upload
|   |-- survey.html, survey.js        # verification survey (replaces the Google Form), drawn from data/survey.json
|   |-- admin.html                    # admin: approve, verify, edit, add, delete, CSV upload
|   |-- admin.js
|   |-- forms.js                      # shared form, validation, geocoding, CSV code
|   |-- supabase-config.js            # public Supabase URL + anon key (written by sync script)
|   `-- styles.css
|-- Data/
|   |-- IRS EO BMF/                   # IRS state CSV files, downloaded by --rebuild (gitignored, 324 MB)
|   `-- ProPublica/
|       |-- category-crosswalk.json   # versioned NTEE-to-GCC mappings (single source of truth)
|       `-- README.md
|-- Docs/
|   |-- Planning/                     # living project documentation
|   |-- Setup/                        # api-keys-setup.md, transfer-guide.md (moving to a new owner)
|   `-- Research and Requirements/    # supplied source material
|-- scripts/
|   |-- build_irs_dataset.py          # IRS filter, normalize, stable IDs, provisional GCC fields
|   |-- category_crosswalk.py         # shared NTEE→GCC resolver used by all ingestion scripts
|   |-- geocode_organizations.py      # Census batch geocoding and ZIP/city fallback
|   |-- normalize_external_data_without_llm.py  # generic external-source adapter
|   |-- enrich_organizations_with_jev.py         # Brave/OpenRouter discovery + Jev classification
|   |-- website_discovery.py          # Brave Search discovery and deterministic contact crawling
|   |-- supabase_store.py             # pipeline reads/writes organizations, caches, API log in Supabase
|   |-- sync_supabase.py              # admin emails -> admins table, writes supabase-config.js
|   |-- build_town_lists.py           # Census place + town names -> app/data/towns/
|   `-- load_environment.py           # .env loader
|-- supabase/
|   |-- config.toml                   # minimal Supabase CLI config for db push
|   `-- migrations/                   # database tables, access rules, pipeline write function
|-- tests/
|   |-- test_build_irs_dataset.py
|   |-- test_enrich_organizations_with_jev.py
|   `-- test_geocode_organizations.py
`-- README.md
```

Organization data lives only in Supabase; `app/data/` holds only fixed settings (filter vocabulary, survey questions, ZIP centroids, town lists).

