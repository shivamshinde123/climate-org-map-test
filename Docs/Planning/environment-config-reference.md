# Environment Configuration Reference

Project-local configuration is read from `.env` without third-party packages. Copyable placeholders and non-secret defaults live in `.env.example`; the real `.env` is ignored by version control. A variable already supplied by the shell takes precedence over the same name in `.env`.

## Command options

`main.py` is the primary entry point. It runs ingestion, geocoding/fallback assignment, validation, and the local server. Its default mode makes no new geocoding requests. `--use-census` explicitly enables Census submissions, and `--no-serve` exits after producing and validating the data.

Existing normalized data and complete coordinates are reused by default. `--rebuild` explicitly regenerates the IRS base. Enrichment skips records already completed under the current discovery prompt, search model, Jev question version, and Jev model.

The ingestion script accepts input directory, code file, output file, and optional record limit arguments. Run its `--help` option for current details.

The geocoding script accepts endpoint, batch-size, limit and `--fallback-only` arguments; it reads and saves organizations and the Census result cache in Supabase. Its default endpoint is the official U.S. Census batch location geocoder. The endpoint is configurable so the provider can be replaced without changing application code.

Future geocoding, map-tile, CRM, and third-party source credentials must be supplied through environment variables and must never be committed. Variable names are TBD.

## Supabase

Migrations in `supabase/migrations/` are applied by the deploy workflow (`supabase db push`, tracked in `supabase_migrations.schema_migrations`); on a new project run them once in the SQL Editor, in order, then `python -m scripts.sync_supabase`. The script records the admin emails and writes `app/supabase-config.js` (public URL and anon key) for the map and forms; re-run it when `ADMIN_EMAILS` changes. The pipeline (`main.py`) reads and writes organizations in Supabase itself, so it needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on every run.

- `SUPABASE_URL`: project URL (Project Settings → API).
- `SUPABASE_ANON_KEY`: public anon key; ends up in `app/supabase-config.js`, which is safe because row-level security protects the data.
- `SUPABASE_SERVICE_ROLE_KEY`: secret; used by the pipeline and the sync script. Never put it in `app/`.
- `ADMIN_EMAILS`: comma-separated emails allowed to use `admin.html`. Each sync makes the `admins` table match this list exactly: new emails are added and emails no longer listed are removed. If it is empty or missing, the table is left unchanged rather than emptied.

GitHub Actions secrets (repository Settings → Secrets and variables → Actions):

- `SUPABASE_DB_URL`: Session pooler connection string with the database password (URL-encoded). Used only by the *migrate* job in `deploy.yml`. GitHub runners have no IPv6, so the direct connection string does not work.
- `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `BRAVE_API_KEY`: used by `pipeline.yml` (the same values as in `.env`). Models use the code defaults (`openai/gpt-5.4-nano`, `typesafe/jev-1.13`); the paid contact lookup stays off. The Supabase URL is read from `app/supabase-config.js`.
- `keep-awake.yml` needs no secret: it reads the public URL and anon key from `app/supabase-config.js`.

In the Supabase dashboard, Authentication → URL Configuration must list the admin page URLs (the GitHub Pages `admin.html` and `http://localhost:8000/admin.html`) as redirect URLs for the email sign-in link.

## Website discovery and Jev classification

Step-by-step account and key creation for both providers: [../Setup/api-keys-setup.md](../Setup/api-keys-setup.md).

`--enrichment-limit N` caps how many organizations a run enriches and `--enrichment-state XX` restricts it to one state (e.g. `MA`). The paid OpenRouter contact lookup for sites that block the crawler is off by default; `--contact-fallback` turns it on (about 2 cents each). Brave results, picker answers, OpenRouter web-search answers, contact lookups and Jev answers are cached in the Supabase `pipeline_cache` table, so re-runs only pay for new work.

Every Brave and OpenRouter request is written to the Supabase `api_log` table, one row per entry (bodies cut at 4,000 characters). `type: "request"` entries hold the provider, purpose (`website_discovery`, `web_search_website_discovery`, `web_search_contact_details`, `jev_classification`), organization id and name, full URL, request body, HTTP status, response headers and body (OpenRouter bodies include `usage.cost`), and duration. `type: "decision"` entries record which path was taken and why (`brave_accepted`, `brave_rejected`, `web_search_fallback`, `contacts_from_site`, `contact_fallback`, cache hits). API keys and cookies are never written. A Brave HTTP 401/403/422 stops the run instead of silently falling back to paid OpenRouter search.

- `BRAVE_API_KEY`: optional but strongly recommended. Enables Brave Search as the primary website-discovery path, which is faster and cheaper than LLM web search for clear-match cases. When absent, every record falls through to the OpenRouter web-search path. Get a key at https://brave.com/search/api/.
- `OPENROUTER_API_KEY`: required. The only LLM key: used for fallback web-search discovery and contact extraction (Chat Completions + `web` plugin) and for Jev classification (Decisions API).
- `SEARCH_MODEL`: optional model override for the Brave-result picker and the web-search fallback; defaults to `openai/gpt-5.4-nano` (an OpenRouter model ID).
- `SEARCH_BASE_URL`: optional chat-completions override; defaults to `https://openrouter.ai/api/v1/chat/completions`.
- `JEV_MODEL`: optional Jev override; defaults to the pinned `typesafe/jev-1.13` model.
- `JEV_BASE_URL`: optional Decisions API override; defaults to `https://openrouter.ai/api/alpha/decisions`.

No key may appear in browser code, generated GeoJSON, caches, command output, or version control. Start with `--enrichment-limit` because discovery and Jev calls consume external API services.

