# Moving the Climate Organizations Map to a new owner

This guide moves the whole project from the current owner's GitHub and Supabase accounts to the new owner's (the CEO's): the code, the public website, the database, the admin page and the verification survey. Plan on about an hour. Every step is done in a web browser or a terminal; no coding is needed.

**The new system lives on the `supabase-database` branch.** The `master` branch is still the old map without a database. This guide makes `supabase-database` the new repository's main branch.

---

## What moves where

| Piece | Now | After the move |
|---|---|---|
| Code | `github.com/shivamshinde123/climate-organization-mapping` (branch `supabase-database`) | A repository in the CEO's GitHub account (main branch `master`) |
| Public website | `shivamshinde123.github.io/climate-organization-mapping/` | `<ceo-username>.github.io/<repo-name>/`, deployed by GitHub Pages from the new repository |
| Database (organizations, admins, survey answers, API caches) | The test Supabase project *Climate-org-mapping* | A new Supabase project in the CEO's account |
| Keys and admin emails | The current owner's `.env` file (never in Git) | A `.env` file with the CEO's keys on whichever computer runs the setup |
| Pipeline source data (IRS files, address lookups, ~330 MB) | `Data/` folders on the current owner's computer (not in Git) | Only needed to re-run the IRS pipeline; see *Optional: pipeline data* |

Supabase is the only place the organizations live: the website and the pipeline both read them from the database. Moving the database (Step 7) moves the map's data.

---

## Before you start

- [ ] **GitHub account for the CEO.** If the new repository will be **private**, the account needs **GitHub Pro or Team**: GitHub Pages does not publish private repositories on the free plan. A public repository works on the free plan.
- [ ] **Supabase account for the CEO** at [supabase.com](https://supabase.com). The free plan allows two active projects.
- [ ] **A computer with Git and Python 3.10 or newer** (check with `git --version` and `python --version`). This can be your computer; the setup only needs the CEO's keys, not the CEO's computer.
- [ ] **The admin email(s):** the address(es) that should be able to use the admin page, normally the CEO's.

---

## Step 1 — Copy the code to the CEO's GitHub

1. Signed in as the CEO, create an **empty** repository on GitHub (**New repository**; do not add a README, license or .gitignore). Choose *Private* (needs GitHub Pro/Team) or *Public*. Note its URL, for example `https://github.com/ceo-username/climate-organizations-map.git`.
2. On the computer you are using, in the project folder:

```powershell
git fetch origin
git switch supabase-database
git pull
```

```powershell
git remote add ceo https://github.com/ceo-username/climate-organizations-map.git
```

```powershell
git push ceo supabase-database:master
```

The last command puts the new system on the CEO's `master` branch with its full history. Git asks you to sign in; use an account with write access to the CEO's repository (the CEO's, or yours after the CEO adds you under **Settings → Collaborators**).

> **Alternative:** to hand over the existing repository itself (history, issues and all), use **Settings → General → Danger Zone → Transfer ownership** in the current repository, then make `supabase-database` the default branch in the new location. Copying (above) leaves the current owner's repository untouched, which is safer while you test.

## Step 2 — Turn on the website (GitHub Pages)

1. In the CEO's repository: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Open the **Actions** tab. The *Deploy to GitHub Pages* workflow runs on every push to `master`. If it has not run yet, open it and click **Run workflow**.
3. When it finishes (green check), the site is at `https://<ceo-username>.github.io/<repo-name>/`. Write this address down; Step 5 needs it.

At this point the map shows the organizations from the data file but has no database yet, so the add form says submissions are not open. That is expected.

## Step 3 — Create the Supabase project

1. Signed in to Supabase as the CEO: **New project**.
2. Name: for example `climate-organizations-map`. Region: a US region (for example *East US*). Set a database password and keep it in a password manager; Step 4 puts it in a GitHub secret.
3. Wait until the project shows as ready (about two minutes).

## Step 4 — Create the tables

1. In the project: **SQL Editor → New query**.
2. Open `supabase/migrations/20261123000000_organizations.sql` from the repository, paste all of it, and click **Run**. It should say *Success. No rows returned*.
3. New query again; paste and run `supabase/migrations/20261123020000_survey_responses.sql`.
4. New query again; paste and run `supabase/migrations/20261124000000_database_only.sql`.
5. New query again; paste and run `supabase/migrations/20261124010000_map_rows.sql`.
6. New query again; paste and run `supabase/migrations/20261124020000_survey_rows_admin_owned.sql`, then `20261124030000_pipeline_runs.sql`, `20261124040000_dispatch_pipeline_runs.sql`, `20261124050000_monthly_irs_refresh.sql` and `20261124060000_admins_in_portal.sql`, the same way.
7. Check **Table Editor**: seven tables, `organizations`, `admins`, `survey_responses`, `pipeline_cache`, `api_log`, `pipeline_runs` and `pipeline_settings`, each marked *RLS enabled*.

These files create the tables and the access rules: visitors can only add pending submissions and survey responses, and only admins can read, approve, edit or delete.

Then let GitHub apply future database changes itself. Every deploy runs `supabase db push`, which applies any new file in `supabase/migrations/` before the site goes live (files already applied are skipped; the first deploy reapplies these once, which is safe).

1. In Supabase: **Connect** (top bar) → **Session pooler** → copy the connection string. Replace `[YOUR-PASSWORD]` with the database password from Step 3. If the password has characters such as `@`, `#` or `/`, URL-encode them (for example `@` becomes `%40`).
2. In the CEO's GitHub repository: **Settings → Secrets and variables → Actions → New repository secret**. Name: `SUPABASE_DB_URL`. Value: the connection string.

Without this secret the deploy stops at the *migrate* step and the site is not updated. Use the Session pooler string, not the direct connection: GitHub's machines can't reach the direct one.

3. For the admin page's *Run extraction* button, add three more secrets the same way, with the same values as in `.env` (Step 6): `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY` and `BRAVE_API_KEY`.
4. Let Supabase start GitHub runs. In GitHub (signed in as the CEO): **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**. Repository access: *Only select repositories* → this repository. Permissions → Repository permissions → **Actions: Read and write**. Expiration: up to one year; **put a reminder in the calendar a week before it expires**. Copy the token, then in the Supabase **SQL Editor** run (with the real values):

```sql
select vault.create_secret('<the token>', 'github_dispatch_token');
select vault.create_secret('<ceo-username>/<repo-name>', 'github_repo');
```

To replace an expired token later: `select vault.update_secret((select id from vault.secrets where name = 'github_dispatch_token'), '<new token>');`. Supabase Vault stores both encrypted; they are never in the repository.

## Step 5 — Set up the admin sign-in

The admin page signs in with a link sent by email, so Supabase must know the site's address.

1. **Authentication → URL Configuration**.
2. **Site URL:** `https://<ceo-username>.github.io/<repo-name>/`
3. **Redirect URLs → Add URL**, add both:
   - `https://<ceo-username>.github.io/<repo-name>/admin.html`
   - `http://localhost:8000/admin.html` (for testing on a computer)
4. **Save.**

Supabase's built-in email sender only sends a few sign-in emails per hour. That is enough for one or two admins. For more, connect a mail service under **Authentication → Emails → SMTP Settings**.

## Step 6 — Put the keys in `.env`

1. In Supabase: **Project Settings → API Keys → Legacy API Keys** tab. If the legacy keys are disabled, enable them; the site is built and tested with them.
2. In the project folder, open `.env` (copy `.env.example` to `.env` if it does not exist) and set:

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<the "anon" "public" key>
SUPABASE_SERVICE_ROLE_KEY=<the "service_role" "secret" key>
ADMIN_EMAILS=ceo@example.org
```

- `SUPABASE_URL` is under **Project Settings → Data API** (or **Connect**), like `https://abcdefghijklmnop.supabase.co`.
- `ADMIN_EMAILS` is only for the first sign-in: the sync in Step 7 adds these emails as admins. After that, add or remove admins on the admin page (*Admins* section); the sync never removes anyone.
- **The service_role key is a secret.** It stays in `.env`, which Git ignores. Never paste it into a file under `app/`, an email or a chat.
- `OPENROUTER_API_KEY` and `BRAVE_API_KEY` are only for re-running the website-discovery pipeline; see `Docs/Setup/api-keys-setup.md` if the CEO will do that.

## Step 7 — Copy the data and connect the site

1. In the **old** project: **Table Editor → organizations → Export → Export table as CSV**. Do the same for `survey_responses` and `pipeline_cache` (saved website searches and category answers, so re-runs don't pay twice). `api_log` is only an audit trail; skip it.
2. In the **new** project: **Table Editor → organizations → Insert → Import data from CSV**, choose the organizations file. Then the same for `survey_responses` and `pipeline_cache`.
3. Check: **SQL Editor** → `select count(*) from organizations;` shows about 20,600.
4. In the project folder:

```powershell
python -m scripts.sync_supabase
```

Expected ending:

```
      Admins: 1
      Wrote app\supabase-config.js
```

This records the admin email(s) and writes the new project's public address and public (anon) key into `app/supabase-config.js`. The anon key is meant to be public; the access rules from Step 4 protect the data. Publish that file:

```powershell
git add app/supabase-config.js
git commit -m "Connect the map to the new Supabase project"
git push ceo supabase-database:master
```

The push redeploys the site (watch the **Actions** tab) and the forms, admin page and survey are now connected.

## Step 8 — Check that everything works

Use the live address from Step 2. Each check takes a minute.

- [ ] **Map:** loads with about 20,500 points; searching for a town shows results.
- [ ] **Add your organization:** submit a test organization named `TEST …`. A window offers to verify it; click **Not now**.
- [ ] **Admin sign-in:** open `admin.html`, enter an admin email, open the emailed link. The page shows *Signed in as …*.
- [ ] **Approve:** the test organization is under *New organizations to approve*. Approve it, reload the map, search for it.
- [ ] **Survey:** open the test organization's popup on the map, click *Claim and verify this listing*, answer the survey, submit.
- [ ] **Review & verify:** on the admin page the response is under *Verification surveys to review*. Click **Review & verify**, then **Save**. On the map the organization now shows *Verified organization*.
- [ ] **Download:** *Download all responses (CSV)* downloads a spreadsheet with your test answers.
- [ ] **Clean up:** on the admin page, search for `TEST`, open each one, **Delete**; delete the test survey response too.

If a check fails, see *Troubleshooting* below.

## Step 9 — Switch over

- [ ] Share the new map address, and the survey address `…/survey.html`, wherever the old ones were used (the GCC website, emails, social posts).
- [ ] **Close the old Google Form** (*Responses → Accepting responses* off). Answers sent there no longer reach the map. Download its responses first if you want to keep them.
- [ ] Decide what to do with the old site and repository: leave them, archive the repository (**Settings → Archive**), or turn off its Pages site (**Settings → Pages**) so people do not find two maps.
- [ ] Pause or delete the old test Supabase project (*Climate-org-mapping*) once the new one works: **Project Settings → General → Pause project / Delete project**.

---

## Optional: pipeline data

The map, forms and admin page do not need these. They are only needed to rebuild the organization list from new IRS data or to discover more websites. They are left out of Git because of their size:

| Folder | Size | What it is |
|---|---|---|
| `Data/IRS EO BMF/` | ~325 MB | IRS source files (`--rebuild` downloads them from the IRS; no need to hand them over) |
| `Data/Geocoding/` | ~2 MB | Census city and ZIP centers (downloaded again automatically if missing) |

Saved website searches, address lookups, category answers and request logs are in the database and move with Step 7. To hand the files over, zip them and share them privately (for example a shared drive folder), then unzip into the same paths in the new copy.

---

## Ongoing tasks after the move

| Task | How |
|---|---|
| Add or remove an admin | Admin page → *Admins*. You can't remove yourself, and the last admin can't be removed. |
| Review new organizations and surveys | `admin.html`: *New organizations to approve* and *Verification surveys to review*. |
| Refresh the data from a new IRS release | Automatic: a daily database check starts an *IRS data refresh* run when the last successful one is 28 days old. It appears in the admin page's run history; new organizations then show in the *waiting* counts for extraction. By hand: `python main.py --rebuild --use-census --no-serve`. |
| Keep the database awake | Automatic: the *Keep Supabase awake* workflow reads one row every 3 days, because free Supabase projects pause after about a week without activity (the map, forms and admin page then stop until someone clicks **Restore** in Supabase). Check the **Actions** tab now and then that it still runs green. If the repository is public, GitHub turns off scheduled workflows after 60 days without commits; **Enable workflow** turns it back on. |
| Change the database | Add a new file to `supabase/migrations/` and push; the deploy applies it. Never edit a file that has already been applied. |

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| Site shows GitHub's 404 page | Pages not set to *GitHub Actions* (Step 2), the workflow has not finished, or the repository is private on a free GitHub plan. |
| Add form says submissions are not open | `app/supabase-config.js` was not committed and pushed after Step 7, or is still empty. |
| Sync stops with *401* or *Invalid API key* | `SUPABASE_SERVICE_ROLE_KEY` is wrong or is the anon key. Use the legacy *service_role* key (Step 6). |
| Map says *The organization data could not be loaded* | `app/supabase-config.js` is empty or not pushed, the project is paused, or Step 7's import was skipped. |
| A run stays *queued* on the admin page | The message under it gives GitHub's answer. *401*: the token in Vault expired or is wrong (Step 4.4). *404*: `github_repo` is wrong, or `pipeline.yml` isn't on `master` yet. Cancel the run, fix it, and run again. |
| Deploy fails at the *migrate* step | `SUPABASE_DB_URL` secret missing or wrong (Step 4): use the Session pooler string with the real password, URL-encoded. The job log shows the database's error. |
| Sync stops with *relation "admins" does not exist* | Step 4 was skipped or a file failed; run the SQL files again. |
| Sign-in link opens an error or the wrong site | The redirect URLs in Step 5 do not match the site address exactly (check `https`, the repository name and `/admin.html`). |
| Admin page says *… is not an admin* | Another admin adds that email under *Admins* (or, with no admin left to do it, add it to `ADMIN_EMAILS` and run the sync). |
| Sign-in email never arrives | Supabase's built-in sender limit (a few per hour); wait, or set up SMTP (Step 5). Check the spam folder. |
| Changes on the admin page do not show on the map | Reload the map; browsers can keep an old copy for a few minutes. |
