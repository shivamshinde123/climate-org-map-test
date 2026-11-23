-- Supabase becomes the only data store: the map, the admin portal and the
-- Python pipeline all read and write the database; no JSON data files remain.
-- Run once in the Supabase SQL Editor (or `supabase db push`) after the
-- earlier migrations.

-- The map now loads every approved organization from the database (it used to
-- load a static GeoJSON snapshot and read only the rows changed since).
drop policy if exists "map reads live changes" on public.organizations;
drop policy if exists "map reads approved organizations" on public.organizations;
create policy "map reads approved organizations" on public.organizations
  for select to anon, authenticated
  using (review_status = 'approved');

-- Pipeline write used by scripts/supabase_store.py with the service role key.
-- Pipeline rows take the pipeline's values. Rows the admin or a visitor added
-- or changed keep every value they have; the pipeline only fills empty fields
-- and updates its own bookkeeping fields (website discovery, Jev, contacts,
-- geocoding), so it can enrich new organizations without undoing an edit.
create or replace function public.sync_pipeline_organizations(rows jsonb) returns integer
language sql set search_path = '' as $$
  with input as (
    select item ->> 'id' as id, item as properties from jsonb_array_elements(rows) as item
  ), written as (
    insert into public.organizations (id, properties, review_status, updated_via)
    select id, properties, 'approved', 'pipeline' from input
    on conflict (id) do update set properties = case
        when public.organizations.updated_via = 'pipeline' then excluded.properties
        else excluded.properties || (
          select coalesce(jsonb_object_agg(key, value), '{}'::jsonb)
          from jsonb_each(public.organizations.properties)
          where value not in ('""'::jsonb, 'null'::jsonb, '[]'::jsonb, '{}'::jsonb)
            and key !~ '^(website_discovery_|jev_|geocod|contact_version|location_precision|enrichment_error)'
        )
      end
      where public.organizations.properties is distinct from excluded.properties
    returning 1
  )
  select count(*)::integer from written;
$$;
revoke execute on function public.sync_pipeline_organizations(jsonb) from public, anon, authenticated;

-- Paid API answers, so a rerun never pays twice for the same question.
-- kind: brave, discovery, websearch, picker, contact, jev.
create table if not exists public.pipeline_cache (
  kind text not null,
  key text not null,
  result jsonb not null,
  created_at timestamptz not null default now(),
  primary key (kind, key)
);

-- Audit log of every Brave/OpenRouter request and routing decision.
create table if not exists public.api_log (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  entry jsonb not null
);

-- Organizations that answered the GCC survey themselves, matched on EIN.
-- `record` holds survey, evidence and survey_categories.
create table if not exists public.survey_verifications (
  ein text primary key,
  record jsonb not null
);

-- No policies: only the service role (the pipeline) can read or write these.
alter table public.pipeline_cache enable row level security;
alter table public.api_log enable row level security;
alter table public.survey_verifications enable row level security;

-- Survey evidence that used to live in Data/Survey/survey-verifications.json.
insert into public.survey_verifications (ein, record)
select item ->> 'ein', item from jsonb_array_elements($data$[{"ein": "871173877", "map_name": "GREEN BEVERLY 107Q INC", "survey_name": "Green Beverly", "survey": "gb_survey", "source_field": "primary", "evidence": "Green Beverly answered the GCC climate-organization survey itself (gb_survey, row b50c2aa3-2445-59e3-8747-0104f586bf7b, verified=Verified).", "recorded_on": "2026-11-08", "survey_categories": {"organization_type": "Nonprofit / Grassroots", "audience_focus": "Residents / Businesses", "adaptation_vs_mitigation": "Both", "advocacy_vs_action": "Action", "climate_categories": "Energy Efficiency", "reach": "Town / City"}}, {"ein": "842275111", "map_name": "GREEN HUDSON", "survey_name": "Green Hudson", "survey": "andover_survey+compiled_survey_4-7-26", "source_field": "primary", "evidence": "Green Hudson answered the GCC climate-organization survey itself (andover_survey, compiled_survey_4-7-26, row d134de5c-b42c-5d1d-96bc-6112f49f716d, verified=Verified); matched to the map by name and city (Hudson, MA).", "recorded_on": "2026-11-08", "survey_categories": {"organization_type": "Nonprofit / Grassroots", "audience_focus": "Residents / Municipality / Businesses", "adaptation_vs_mitigation": "Both", "advocacy_vs_action": "Both", "climate_categories": "Energy Efficiency", "reach": "Town / City"}}, {"ein": "874054939", "map_name": "TOWNGREEN INC", "survey_name": "TownGreen Inc", "survey": "gb_survey", "source_field": "primary", "evidence": "TownGreen Inc answered the GCC climate-organization survey itself (gb_survey, row 5fa5a8aa-8052-575b-8e5c-ede4c8cff935, verified=Verified); matched to the map by name and city (Gloucester, MA).", "recorded_on": "2026-11-08", "survey_categories": {"audience_focus": "Residents", "adaptation_vs_mitigation": "Mitigation", "advocacy_vs_action": "Both", "climate_categories": "Energy Efficiency", "reach": "Town / City"}}, {"ein": "824681147", "map_name": "SUSTAINABLE MARBLEHEAD", "survey_name": "Sustainable Marblehead", "survey": "compiled_survey_4-7-26", "source_field": "primary", "evidence": "Sustainable Marblehead answered the GCC climate-organization survey itself (compiled_survey_4-7-26, row 574e63ff-09a8-54f8-aca4-ed72fa23b33d, verified=Verified); matched to the map by name and city (Marblehead, MA).", "recorded_on": "2026-11-08", "survey_categories": {"organization_type": "Nonprofit / Grassroots", "audience_focus": "Residents / Municipality / Businesses", "adaptation_vs_mitigation": "Both", "advocacy_vs_action": "Both", "climate_categories": "Energy Efficiency", "reach": "Town / City"}}, {"ein": "030446859", "map_name": "GULF OF MAINE INSTITUTE INC", "survey_name": "Gulf of Maine Institute", "survey": "compiled_survey_4-7-26", "source_field": "primary", "evidence": "Gulf of Maine Institute answered the GCC climate-organization survey itself (compiled_survey_4-7-26, row 16f81520-2470-5944-9344-c6b834093733, verified=Verified); matched to the map by name and city (West Newbury, MA).", "recorded_on": "2026-11-08", "survey_categories": {"organization_type": "Nonprofit / Grassroots", "adaptation_vs_mitigation": "Both", "advocacy_vs_action": "Action", "climate_categories": "Environmental", "reach": "Town / City"}}, {"ein": "474993870", "map_name": "SEASIDE SUSTAINABILITY INC", "survey_name": "Seaside Sustainability", "survey": "compiled_survey_4-7-26", "source_field": "primary", "evidence": "Seaside Sustainability answered the GCC climate-organization survey itself (compiled_survey_4-7-26, row ae358179-bf8a-57b3-8a86-5ba2bb34c59f, verified=Verified); matched to the map by name and city (Gloucester, MA).", "recorded_on": "2026-11-08", "survey_categories": {"organization_type": "Nonprofit / Grassroots", "audience_focus": "Residents / Municipality / Businesses", "advocacy_vs_action": "Both", "climate_categories": "Environmental", "reach": "Town / City"}}, {"ein": "884030374", "map_name": "LEXINGTON CLIMATE ACTION NETWORK INC", "survey_name": "Lexington Climate Action Network", "survey": "compiled_survey_4-7-26", "source_field": "primary", "evidence": "Lexington Climate Action Network answered the GCC climate-organization survey itself (compiled_survey_4-7-26, row e7c6d14a-cee9-5394-9bd1-45bae138276a, verified=Verified); matched to the map by name and city (Lexington, MA).", "recorded_on": "2026-11-08", "survey_categories": {"audience_focus": "Residents / Municipality", "adaptation_vs_mitigation": "Mitigation", "advocacy_vs_action": "Both", "climate_categories": "Energy Efficiency", "reach": "Town / City"}}, {"ein": "992177830", "map_name": "CLIMATE JUSTICE HIVE", "survey_name": "Climate Justice Hive", "survey": "compiled_survey_4-7-26", "source_field": "primary", "evidence": "Climate Justice Hive answered the GCC climate-organization survey itself (compiled_survey_4-7-26, row 681c06c4-5b65-55bf-a6c3-d377cd4493eb, verified=Verified); matched to the map by name and city (Boulder, CO).", "recorded_on": "2026-11-08", "survey_categories": {"organization_type": "Nonprofit / Grassroots", "audience_focus": "Municipality / Businesses", "adaptation_vs_mitigation": "Adaptation", "advocacy_vs_action": "Both", "climate_categories": "Energy Efficiency", "reach": "Town / City"}}, {"ein": "202678120", "map_name": "CAPE ANN VERNAL POND TEAM INC", "survey_name": "Cape AnnVernal Pond Team", "survey": "compiled_survey_4-7-26", "source_field": "primary", "evidence": "Cape AnnVernal Pond Team answered the GCC climate-organization survey itself (compiled_survey_4-7-26, row 59576d96-dc3a-5fb6-9d6f-41aebb376d66, verified=Verified); matched to the map by name and city (Gloucester, MA).", "recorded_on": "2026-11-08", "survey_categories": {"organization_type": "Nonprofit / Grassroots", "climate_categories": "Environmental"}}]$data$::jsonb) as item
on conflict (ein) do update set record = excluded.record;
