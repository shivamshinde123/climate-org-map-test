# Environment Configuration Reference

Project-local configuration is read from `.env` without third-party packages. Copyable placeholders and non-secret defaults live in `.env.example`; the real `.env` is ignored by version control. A variable already supplied by the shell takes precedence over the same name in `.env`.

## Command options

`main.py` is the primary entry point. It runs ingestion, geocoding/fallback assignment, validation, and the local server. Its default mode makes no new geocoding requests. `--use-census` explicitly enables Census submissions, and `--no-serve` exits after producing and validating the data.

Existing normalized data and complete coordinates are reused by default. `--rebuild` explicitly regenerates the IRS base. Enrichment skips records already completed under the current discovery prompt, search model, Jev question version, and Jev model.

The ingestion script accepts input directory, code file, output file, and optional record limit arguments. Run its `--help` option for current details.

The geocoding script accepts input, output, cache, endpoint, batch-size, and optional limit arguments. Its default endpoint is the official U.S. Census batch location geocoder. The endpoint is configurable so the provider can be replaced without changing application code.

Future geocoding, map-tile, CRM, and third-party source credentials must be supplied through environment variables and must never be committed. Variable names are TBD.

## Website discovery and Jev classification

- `OPENAI_API_KEY`: required for official-website discovery and evidence-based summary generation using web search.
- `OPENROUTER_API_KEY`: required for Jev classification through OpenRouter's Decisions API.
- `OPENAI_MODEL`: optional website-search model override; defaults to `gpt-5.4-mini`.
- `JEV_MODEL`: optional Jev override; defaults to the pinned `typesafe/jev-1.13` model.
- `JEV_BASE_URL`: optional Decisions API override; defaults to `https://openrouter.ai/api/alpha/decisions`.

Neither key may appear in browser code, generated GeoJSON, caches, command output, or version control. Start with `--enrichment-limit` because website discovery and Jev calls consume external API services.

