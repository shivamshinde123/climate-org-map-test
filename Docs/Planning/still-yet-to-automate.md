# Still Yet to Automate

Last reviewed: 2026-11-23

What still needs a person to run or click something, and what should stay manual.
Tick an item off and move it to "Done" when it is automated.

## Already automated

- Visitor submissions ("Add New Organization"), the verification survey, the
  "Verify Organization" step after adding, and CSV uploads all write straight to
  Supabase and wait in the admin review queues.
- The map shows approved changes on load; no redeploy is needed.
- GitHub Actions deploys the site on every push to `master` (`.github/workflows/deploy.yml`).

## To automate (priority order)

- [ ] **Run the extraction pipeline from the admin portal.** Website, contact,
  description and Jev classification enrichment runs only as
  `python main.py --enrich-with-jev ...` on a laptop. Plan: admin picks a state and
  clicks "Run extraction" → Supabase Edge Function (checks the caller is an admin,
  holds a GitHub token) → GitHub Actions `workflow_dispatch` with the state as input →
  pipeline skips organizations already enriched and processes the rest. Show the
  pending count and a per-run limit (`--enrichment-limit`) before confirming, to cap cost.
  Run one job at a time (`concurrency:` on the workflow).
- [ ] **Apply database migrations on deploy.** New files in `supabase/migrations/`
  are applied by hand (dashboard SQL editor or `supabase db push`). Add a
  `supabase db push` step to GitHub Actions so code and schema never drift.
- [ ] **Keep the Supabase project awake.** Free-plan projects pause after about a week
  without activity; restoring is manual. Add a scheduled GitHub Action that pings
  the database every few days, or move to the Pro plan.
- [ ] **Refresh IRS source data.** The `eo_*.csv` files (`Data/IRS EO BMF/`, gitignored)
  are downloaded by hand and nothing checks for a newer release. A monthly GitHub
  Action could download them and rerun the import and geocoding.
- [ ] **Run geocoding for new organizations.** Census geocoding runs from
  `python main.py --use-census` on a laptop. Fold it into the same scheduled or
  admin-triggered pipeline run.
- [ ] **Manage admins in the portal.** Adding or removing an admin means editing
  `ADMIN_EMAILS` and rerunning the sync. An "Admins" section in the admin portal
  would remove that step.
- [ ] **Pipeline results to Supabase.** Previously a separate
  `python scripts/sync_supabase.py` run. Being replaced by the database-only
  migration (pipeline reads and writes Supabase directly); tick off once merged.

## Manual on purpose (keep manual)

- **Approvals.** New organizations, verification responses, post-submission
  verifications and CSV rows appear on the map only after an admin approves them.
- **Quality review of extraction.** Spot-check Jev classifications and the
  websites, emails and phones found, especially after a model or prompt change.
- **Reviewing geocoding misses.** Organizations placed at a ZIP or city center, or
  with no map point, need a human look (or the "Find latitude & longitude" button).

## Rare, fine as manual scripts

These change only when the code or the Census data changes.

- Survey questions: edit `app/data/survey.json`.
- Town lists and ZIP centers: `python scripts/build_town_lists.py`.
- ProPublica category crosswalk: `scripts/category_crosswalk.py`,
  `scripts/analyze_propublica_categories.py`.

## Done

_Nothing moved here yet._
