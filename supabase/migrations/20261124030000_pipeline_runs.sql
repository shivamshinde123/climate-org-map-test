-- Run requests for the extraction pipeline. An admin (or the monthly schedule)
-- adds a row; a GitHub Actions run picks it up and writes back its status,
-- counts and log link. Safe to run again.

create table if not exists public.pipeline_runs (
  id bigint generated always as identity primary key,
  -- extract: website/contact/summary/Jev for one state. irs_refresh: download
  -- IRS files, rebuild, geocode (no paid calls).
  kind text not null default 'extract' check (kind in ('extract', 'irs_refresh')),
  state text check (state ~ '^[A-Z]{2}$'),
  -- Organizations per run: caps spend and keeps a run inside GitHub's 6-hour job limit.
  org_limit integer check (org_limit between 1 and 1000),
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  requested_by text default (auth.jwt() ->> 'email'),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  run_url text,
  summary jsonb,
  error text,
  check (kind <> 'extract' or (state is not null and org_limit is not null))
);

-- One run at a time, so two runs never pay for the same organizations.
create unique index if not exists pipeline_runs_one_active
  on public.pipeline_runs ((true)) where status in ('queued', 'running');

alter table public.pipeline_runs enable row level security;

-- Admins see the history, request runs, and can mark a queued or stuck run
-- cancelled (a run that never started would otherwise block every later one).
-- Only the service role (the GitHub run) sets the other columns.
revoke all on public.pipeline_runs from anon, authenticated;
grant select on public.pipeline_runs to authenticated;
grant insert (kind, state, org_limit) on public.pipeline_runs to authenticated;
grant update (status) on public.pipeline_runs to authenticated;

drop policy if exists "admin reads runs" on public.pipeline_runs;
drop policy if exists "admin requests runs" on public.pipeline_runs;
drop policy if exists "admin cancels runs" on public.pipeline_runs;
create policy "admin reads runs" on public.pipeline_runs
  for select to authenticated using (public.is_admin());
create policy "admin requests runs" on public.pipeline_runs
  for insert to authenticated with check (public.is_admin() and status = 'queued');
create policy "admin cancels runs" on public.pipeline_runs
  for update to authenticated
  using (public.is_admin() and status in ('queued', 'running'))
  with check (status = 'cancelled');

-- The settings the last extraction run used. The pipeline writes this row at
-- the start of every extraction, so the pending count below follows code
-- version bumps and model changes without a migration.
create table if not exists public.pipeline_settings (
  id boolean primary key default true check (id),
  discovery_version text not null,
  search_model text not null,
  jev_model text not null,
  jev_questions_version text not null,
  contact_version text not null,
  updated_at timestamptz not null default now()
);
insert into public.pipeline_settings
  (discovery_version, search_model, jev_model, jev_questions_version, contact_version)
values ('gcc-website-discovery-v8', 'openai/gpt-5.4-nano', 'typesafe/jev-1.13', 'gcc-jev-classification-v2', 'gcc-contacts-v3')
on conflict (id) do nothing;

alter table public.pipeline_settings enable row level security;
revoke all on public.pipeline_settings from anon, authenticated;
grant select on public.pipeline_settings to authenticated;
drop policy if exists "admin reads settings" on public.pipeline_settings;
create policy "admin reads settings" on public.pipeline_settings
  for select to authenticated using (public.is_admin());

-- Organizations per state that an extraction run would still process.
-- Same rule as enrichment_is_complete() in scripts/enrich_organizations_with_jev.py;
-- change both together.
create or replace function public.extraction_pending()
returns table (state text, pending bigint)
language sql stable security invoker set search_path = '' as $$
  select o.properties ->> 'state', count(*)
  from public.organizations o
  cross join public.pipeline_settings s
  where o.review_status = 'approved'
    and coalesce(o.properties ->> 'source', '') <> 'GCC survey'
    and not coalesce(
      o.properties ->> 'website_discovery_version' = s.discovery_version
      and o.properties ->> 'website_discovery_model' = s.search_model
      and (
        o.properties ->> 'website_discovery_status' in ('not_found', 'ambiguous')
        or (o.properties ->> 'website_discovery_status' = 'found'
            and coalesce(o.properties ->> 'verification_source', '') like 'GCC survey%'
            and o.properties ->> 'contact_version' = s.contact_version)
        or (o.properties ->> 'website_discovery_status' = 'found'
            and coalesce(o.properties ->> 'verification_source', '') not like 'GCC survey%'
            and o.properties ->> 'jev_classification_status' = 'classified'
            and o.properties ->> 'jev_requested_model' = s.jev_model
            and o.properties ->> 'jev_questions_version' = s.jev_questions_version
            and o.properties ->> 'contact_version' = s.contact_version)
      ),
      false)
  group by 1
  order by 1;
$$;
revoke execute on function public.extraction_pending() from public, anon;
grant execute on function public.extraction_pending() to authenticated;
