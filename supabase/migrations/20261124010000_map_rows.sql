-- One fast request for the map. Reading fields out of every organization's
-- full `properties` (37 MB) took ~1 s per 1,000-row page, and the map's 21
-- parallel pages hit the database's time limit. A stored compact row per
-- organization, kept up to date by Postgres on every write, lets one query
-- return all of them in ~50 ms.

-- The fields the map needs, as one compact array. Order must match MAP_FIELDS
-- in app/app.js. Declared immutable so a generated column can use it:
-- jsonb_build_array is only "stable" because it accepts any type, but for
-- jsonb inputs the result depends on nothing but the input.
create or replace function public.organization_map_row(p jsonb) returns jsonb
language sql immutable parallel safe set search_path = '' as $$
  select jsonb_build_array(
    p -> 'id', p -> 'name', p -> 'address', p -> 'city', p -> 'state', p -> 'postal_code', p -> 'source_id',
    p -> 'gcc_organization_type', p -> 'gcc_audience_focus', p -> 'gcc_resilience', p -> 'gcc_activity',
    p -> 'gcc_action_category', p -> 'gcc_climate_category', p -> 'gcc_reach', p -> 'gcc_verification',
    p -> 'latitude', p -> 'longitude'
  );
$$;

alter table public.organizations add column if not exists map jsonb
  generated always as (public.organization_map_row(properties)) stored;

-- Every organization the caller may read (row-level security applies: visitors
-- see approved rows only), as one JSON array of map rows.
create or replace function public.map_organizations() returns json
language sql stable security invoker set search_path = '' as $$
  select coalesce(json_agg(map), '[]'::json) from public.organizations where review_status = 'approved';
$$;
grant execute on function public.map_organizations() to anon, authenticated;
