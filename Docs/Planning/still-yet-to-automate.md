# Still Yet to Automate

Last reviewed: 2026-11-24

What still needs a person to run or click something, and what should stay manual.
Tick an item off and move it to "Done" when it is automated.

## Already automated

- Visitor submissions ("Add New Organization"), the verification survey, the
  "Verify Organization" step after adding, and CSV uploads all write straight to
  Supabase and wait in the admin review queues.
- The map shows approved changes on load; no redeploy is needed.
- GitHub Actions deploys the site on every push to `master` (`.github/workflows/deploy.yml`).

## To automate (in order)

Design: Supabase holds all data and every run request; GitHub Actions only computes
and deploys. Each run (admin click or monthly schedule) is a row in a
`pipeline_runs` table that one pipeline workflow picks up and reports back to.
Nothing here merges to `master` until the manager approves; GitHub can only start
workflows that exist on `master`, so phases C and D are tested end to end after a merge.

### B. Pipeline depends only on Supabase (needed before it can run on GitHub)

- [ ] **Census lookup cache into Supabase.** `Data/Geocoding/census_geocodes.csv`
  becomes `pipeline_cache` kind `census`, shared by laptop and GitHub runs.
  (City and ZIP centroid files stay local: public Census data the code downloads
  when missing.)
- [ ] **Survey organizations owned by the database.** Mark the survey-only and
  survey-verified rows as admin-owned (the merge rule then keeps their values), and
  delete `Data/Survey/survey-organizations.csv`, the `survey_verifications` table
  and the code that re-adds them each run. Verification is now the admin portal's job.
- [ ] **IRS files downloaded by the run.** `eo_*.csv` (51 files, 325 MB) come from
  irs.gov when a rebuild needs them instead of being downloaded by hand.

### C. Run extraction from the admin portal (includes geocoding)

- [ ] `pipeline_runs` table (one queued/running row at a time), a trigger that calls
  GitHub `workflow_dispatch` through `pg_net`, with the GitHub token in Supabase Vault
  (ships as a migration; no Edge Function to deploy).
- [ ] Pipeline workflow: `main.py --enrich-with-jev --enrichment-state XX
  --enrichment-limit N`, `concurrency: pipeline`, writes status, counts and the run
  link back to its row.
- [ ] Admin panel: state, pending count, per-run limit, cost estimate (~$0.012 per
  organization from the MA and CA runs), run history; flags a run queued > 10 minutes
  (likely an expired token).

### D. Monthly IRS refresh

- [ ] Scheduled workflow inserts a `pipeline_runs` row of kind `irs_refresh`:
  download, rebuild, geocode. No paid extraction; new organizations show up in C's
  pending count.

### E. Manage admins in the portal

- [ ] Admin-only access rules on `admins` (guard: the last admin can't be removed).
  `ADMIN_EMAILS` + `scripts/sync_supabase.py` then only bootstrap the first admin.

### Limits that shape the design

- Private repository: 2,000 Actions minutes a month (3,000 with Pro), 6-hour job cap,
  so every run has an organization limit. A cut-off run keeps finished records and
  cached paid answers.
- OpenRouter key limit is the hard spend cap.
- The GitHub token in Vault expires (max one year): calendar reminder to renew.
- Stop laptop extraction runs once C works, so two runs never pay for the same records.

## Manual on purpose (keep manual)

- **One-time setup:** GitHub secrets (`SUPABASE_DB_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `OPENROUTER_API_KEY`, `BRAVE_API_KEY`), the GitHub token in Vault, GitHub Pages.
- **Money:** topping up OpenRouter credit and raising the key limit.

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

## Done (phase A, on the `supabase-database` branch)

- [x] **Pipeline results to Supabase.** The pipeline reads and writes Supabase
  directly (`scripts/supabase_store.py`); no separate sync run.
- [x] **Apply database migrations on deploy.** `deploy.yml` runs `supabase db push`
  before publishing (secret `SUPABASE_DB_URL`). On the `supabase-database` branch;
  active once merged to `master` and the secret is added.
- [x] **Keep the Supabase project awake.** `keep-awake.yml` reads one row every 3 days
  with the public anon key. On the `supabase-database` branch; GitHub runs schedules
  from the default branch only, so it starts once merged.
