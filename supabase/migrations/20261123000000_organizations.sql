-- Organizations database for the Climate Organizations Map.
-- Run once in the Supabase SQL Editor (or `supabase db push`).
--
-- One row per map organization. `properties` holds the same object as a
-- GeoJSON feature's properties, so the map and the pipeline share one shape.
-- `updated_via` records who last changed a row:
--   pipeline     - loaded by scripts/sync_supabase.py from the Python pipeline
--   admin        - added or edited by the admin on admin.html
--   public_form  - submitted by a visitor on add.html (pending until approved)
-- The pipeline never overwrites a row the admin or a visitor changed.

create table if not exists public.organizations (
  id text primary key,
  properties jsonb not null,
  review_status text not null default 'approved'
    check (review_status in ('pending', 'approved', 'rejected', 'removed')),
  updated_via text not null default 'pipeline'
    check (updated_via in ('pipeline', 'admin', 'public_form')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Read-only copies for searching and sorting; always derived from properties.
  name text generated always as (properties ->> 'name') stored,
  city text generated always as (properties ->> 'city') stored,
  state text generated always as (properties ->> 'state') stored,
  verification text generated always as (properties ->> 'gcc_verification') stored
);

create index if not exists organizations_changed_idx
  on public.organizations (updated_via, review_status) where updated_via <> 'pipeline';

create or replace function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists organizations_touch on public.organizations;
create trigger organizations_touch before update on public.organizations
  for each row execute function public.touch_updated_at();

-- Admin emails. No policies: only the service role (sync script) can read or write it.
create table if not exists public.admins (email text primary key);
alter table public.admins enable row level security;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from admins where lower(email) = lower(auth.jwt() ->> 'email'));
$$;
-- Only signed-in users need it; it reveals nothing but the caller's own status.
revoke execute on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated;

alter table public.organizations enable row level security;

drop policy if exists "map reads live changes" on public.organizations;
drop policy if exists "visitors submit pending organizations" on public.organizations;
drop policy if exists "admin manages organizations" on public.organizations;

-- The map reads only rows changed outside the pipeline that are live or removed.
create policy "map reads live changes" on public.organizations
  for select to anon, authenticated
  using (updated_via <> 'pipeline' and review_status in ('approved', 'removed'));

-- Visitors may only add new, unverified, pending rows of bounded size.
create policy "visitors submit pending organizations" on public.organizations
  for insert to anon, authenticated
  with check (
    review_status = 'pending'
    and updated_via = 'public_form'
    and properties ->> 'gcc_verification' = 'Not Verified'
    and properties ->> 'status' = 'Not Verified'
    and pg_column_size(properties) < 16000
  );

-- The admin can read and change everything.
create policy "admin manages organizations" on public.organizations
  for all to authenticated
  using (public.is_admin())
  with check (public.is_admin());

-- Bulk load used by scripts/sync_supabase.py with the service role key.
-- Rows changed by the admin or a visitor are left alone.
create or replace function public.sync_pipeline_organizations(rows jsonb) returns integer
language sql set search_path = '' as $$
  with input as (
    select item ->> 'id' as id, item as properties from jsonb_array_elements(rows) as item
  ), written as (
    insert into public.organizations (id, properties, review_status, updated_via)
    select id, properties, 'approved', 'pipeline' from input
    on conflict (id) do update set properties = excluded.properties
      where public.organizations.updated_via = 'pipeline'
        and public.organizations.properties is distinct from excluded.properties
    returning 1
  )
  select count(*)::integer from written;
$$;
revoke execute on function public.sync_pipeline_organizations(jsonb) from public, anon, authenticated;
