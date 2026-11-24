-- Start a GitHub Actions run (.github/workflows/pipeline.yml) for every new
-- pipeline_runs row. The call goes out through pg_net, so the request that
-- added the row doesn't wait for GitHub. Needs two Vault secrets, added once
-- by hand (they never go in git):
--   select vault.create_secret('<GitHub token>', 'github_dispatch_token');
--   select vault.create_secret('<owner>/<repository>', 'github_repo');
-- The token is a fine-grained personal access token for this one repository
-- with "Actions: Read and write". Safe to run again.

create extension if not exists pg_net;

-- pg_net's request id, to look up GitHub's answer (kept by pg_net for 6 hours).
alter table public.pipeline_runs add column if not exists dispatch_request_id bigint;

create or replace function public.dispatch_pipeline_run() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  token text := (select decrypted_secret from vault.decrypted_secrets where name = 'github_dispatch_token');
  repo text := (select decrypted_secret from vault.decrypted_secrets where name = 'github_repo');
  request_id bigint;
begin
  if token is null or repo is null then
    -- Fail the row at once so it doesn't hold the one-active-run slot.
    update public.pipeline_runs
    set status = 'failed', finished_at = now(),
        error = 'Not started: github_dispatch_token or github_repo is missing from Supabase Vault.'
    where id = new.id;
    return null;
  end if;
  request_id := net.http_post(
    url := 'https://api.github.com/repos/' || repo || '/actions/workflows/pipeline.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'climate-org-map',
      'Content-Type', 'application/json'),
    body := jsonb_build_object('ref', 'master', 'inputs', jsonb_build_object('run_id', new.id::text)));
  update public.pipeline_runs set dispatch_request_id = request_id where id = new.id;
  return null;
end;
$$;
revoke execute on function public.dispatch_pipeline_run() from public, anon, authenticated;

drop trigger if exists pipeline_runs_dispatch on public.pipeline_runs;
create trigger pipeline_runs_dispatch after insert on public.pipeline_runs
  for each row execute function public.dispatch_pipeline_run();

-- GitHub's answer to a run's start request, for the admin portal: 204 means
-- GitHub accepted it. Anything else (401 expired token, 404 workflow not on
-- master) explains a run that stays queued. Null while pending or after pg_net
-- has discarded the answer.
create or replace function public.pipeline_dispatch_result(run_id bigint)
returns table (status_code integer, message text)
language sql stable security definer set search_path = '' as $$
  select r.status_code, coalesce(left(r.content, 300), r.error_msg)
  from public.pipeline_runs p
  join net._http_response r on r.id = p.dispatch_request_id
  where p.id = run_id and public.is_admin();
$$;
revoke execute on function public.pipeline_dispatch_result(bigint) from public, anon;
grant execute on function public.pipeline_dispatch_result(bigint) to authenticated;
