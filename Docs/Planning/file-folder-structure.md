# File and Folder Structure

```text
Climate Org Mapping/
|-- .env                           # local secrets; ignored
|-- .env.example                   # safe configuration template
|-- .gitignore
|-- main.py                        # complete build, geocode, validate, and serve entry point
|-- app/
|   |-- data/
|   |   `-- organizations.geojson  # generated
|   |   `-- map-schema.json         # filter and field vocabulary
|   |-- app.js
|   |-- index.html
|   `-- styles.css
|-- Data/                           # supplied IRS CSV files
|-- Docs/
|   |-- Planning/                   # living project documentation
|   `-- Research and Requirements/  # supplied source material
|-- scripts/
|   |-- build_irs_dataset.py
|   |-- geocode_organizations.py
|   |-- normalize_external_data_without_llm.py
|   |-- enrich_organizations_with_jev.py
|   `-- load_environment.py
|-- tests/
|   |-- test_build_irs_dataset.py
|   `-- test_geocode_organizations.py
`-- README.md
```

Generated artifacts should be reproducible from source data and scripts.

