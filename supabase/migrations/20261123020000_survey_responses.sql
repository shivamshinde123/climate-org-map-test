-- Responses to the Localized Climate Action survey (survey.html), which
-- replaces the Google Form "Climate Organizations Map VERIFICATION".
--
-- `answers` maps each question id in app/data/survey.json to its answer (text,
-- or a list for check boxes). Responses hold names and emails, so only admins
-- can read them; visitors can only add one.
--   pending   - an organization's response waiting for the admin to verify it on the map
--   approved  - the admin applied it to the map (applied_organization_id)
--   research  - a municipal or individual response; nothing to apply to the map

create table if not exists public.survey_responses (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  connection text not null check (connection in ('organization', 'municipality', 'individual')),
  organization_id text,          -- map listing the survey was opened from ("Claim and verify"), if any
  answers jsonb not null,
  review_status text not null check (review_status in ('pending', 'approved', 'research')),
  applied_organization_id text,
  reviewed_at timestamptz
);

create index if not exists survey_responses_pending_idx on public.survey_responses (created_at) where review_status = 'pending';

alter table public.survey_responses enable row level security;

drop policy if exists "visitors submit survey responses" on public.survey_responses;
drop policy if exists "admin manages survey responses" on public.survey_responses;

create policy "visitors submit survey responses" on public.survey_responses
  for insert to anon, authenticated
  with check (
    review_status = (case when connection = 'organization' then 'pending' else 'research' end)
    and applied_organization_id is null
    and reviewed_at is null
    and jsonb_typeof(answers) = 'object'
    and pg_column_size(answers) < 64000
  );

create policy "admin manages survey responses" on public.survey_responses
  for all to authenticated
  using (public.is_admin())
  with check (public.is_admin());
