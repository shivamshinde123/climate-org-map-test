-- The database, not files, now owns survey organizations. Until now every
-- pipeline run re-added the survey-only organizations from
-- Data/Survey/survey-organizations.csv and re-applied the survey answers in
-- survey_verifications, so an IRS rebuild could not overwrite them. Marking
-- those rows admin-owned gives the same protection through the normal merge
-- rule (sync_pipeline_organizations keeps an admin row's non-empty values),
-- and new verifications come from the admin portal. Safe to run again.

update public.organizations
set updated_via = 'admin'
where updated_via = 'pipeline'
  and (properties ->> 'source' = 'GCC survey'
       or properties ->> 'verification_source' like 'GCC survey%');

drop table if exists public.survey_verifications;
