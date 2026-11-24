-- Monthly IRS refresh: a daily pg_cron check queues an irs_refresh run (the
-- pipeline_runs trigger then starts it on GitHub) when the last successful
-- refresh is 28 or more days old. The IRS republishes the EO BMF about monthly.
-- A failed refresh is retried the next day; a day with another run queued or
-- running is skipped. The run downloads only files the IRS changed, rebuilds,
-- and geocodes new addresses; it makes no paid calls (new organizations then
-- show up in the admin page's waiting counts).
-- Meant to arrive with the merge to master (deploy applies it), because it
-- starts .github/workflows/pipeline.yml, which GitHub runs only from master.
-- Safe to run again.

create extension if not exists pg_cron;

create or replace function public.queue_irs_refresh() returns void
language sql security definer set search_path = '' as $$
  insert into public.pipeline_runs (kind)
  select 'irs_refresh'
  where not exists (select 1 from public.pipeline_runs
                    where kind = 'irs_refresh' and status = 'succeeded' and created_at > now() - interval '28 days')
    and not exists (select 1 from public.pipeline_runs
                    where kind = 'irs_refresh' and created_at > now() - interval '20 hours')
    and not exists (select 1 from public.pipeline_runs where status in ('queued', 'running'));
$$;
revoke execute on function public.queue_irs_refresh() from public, anon, authenticated;

-- 09:00 UTC daily (04:00 or 05:00 in Massachusetts). Same name = replaced, not duplicated.
select cron.schedule('irs-refresh', '0 9 * * *', 'select public.queue_irs_refresh()');
