# File and Folder Structure

```text
Climate Org Mapping/
|-- .env                              # local secrets; ignored
|-- .env.example                      # safe configuration template
|-- .gitignore
|-- main.py                           # complete build, geocode, validate, and serve entry point
|-- .github/
|   `-- workflows/
|       `-- deploy.yml                # GitHub Actions: auto-deploys app/ to GitHub Pages on push
|-- app/
|   |-- data/
|   |   |-- organizations.geojson     # generated
|   |   `-- map-schema.json           # filter and field vocabulary
|   |-- app.js                        # map; overlays live changes from Supabase
|   |-- index.html
|   |-- add.html                      # public "Add your organization" form and CSV upload
|   |-- admin.html                    # admin: approve, verify, edit, add, delete, CSV upload
|   |-- admin.js
|   |-- forms.js                      # shared form, validation, geocoding, CSV code
|   |-- supabase-config.js            # public Supabase URL + anon key (written by sync script)
|   `-- styles.css
|-- Data/
|   |-- IRS EO BMF/                   # supplied IRS state CSV files (gitignored, 324 MB)
|   `-- ProPublica/
|       |-- category-crosswalk.json   # versioned NTEE-to-GCC mappings (single source of truth)
|       `-- README.md
|-- Docs/
|   |-- Planning/                     # living project documentation
|   `-- Research and Requirements/    # supplied source material
|-- scripts/
|   |-- build_irs_dataset.py          # IRS filter, normalize, stable IDs, provisional GCC fields
|   |-- category_crosswalk.py         # shared NTEE→GCC resolver used by all ingestion scripts
|   |-- geocode_organizations.py      # Census batch geocoding and ZIP/city fallback
|   |-- normalize_external_data_without_llm.py  # generic external-source adapter
|   |-- enrich_organizations_with_jev.py         # Brave/OpenRouter discovery + Jev classification
|   |-- website_discovery.py          # Brave Search discovery and deterministic contact crawling
|   |-- sync_supabase.py              # loads the GeoJSON into Supabase, writes supabase-config.js
|   `-- load_environment.py           # .env loader
|-- supabase/
|   `-- migrations/                   # database tables, access rules, sync function
|-- tests/
|   |-- test_build_irs_dataset.py
|   |-- test_enrich_organizations_with_jev.py
|   `-- test_geocode_organizations.py
`-- README.md
```

Generated artifacts should be reproducible from source data and scripts.

