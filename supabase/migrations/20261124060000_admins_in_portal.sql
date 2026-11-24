-- Admins manage the admin list on the admin page. An admin can add an email
-- and remove another admin, never themselves, and the last admin can't be
-- removed by anyone, so the page can't lock everyone out.
-- scripts/sync_supabase.py now only adds ADMIN_EMAILS (first-admin setup).
-- Safe to run again.

revoke all on public.admins from anon;
revoke update on public.admins from authenticated;
grant select, insert, delete on public.admins to authenticated;

-- is_admin() compares lowercase; storing lowercase keeps one row per person.
alter table public.admins drop constraint if exists admins_email_lowercase;
alter table public.admins add constraint admins_email_lowercase
  check (email = lower(email) and email like '%_@_%._%');

drop policy if exists "admins read admins" on public.admins;
drop policy if exists "admins add admins" on public.admins;
drop policy if exists "admins remove other admins" on public.admins;
create policy "admins read admins" on public.admins
  for select to authenticated using (public.is_admin());
create policy "admins add admins" on public.admins
  for insert to authenticated with check (public.is_admin());
create policy "admins remove other admins" on public.admins
  for delete to authenticated
  using (public.is_admin() and email <> lower(auth.jwt() ->> 'email'));

create or replace function public.keep_one_admin() returns trigger
language plpgsql set search_path = '' as $$
begin
  if (select count(*) from public.admins) <= 1 then
    raise exception 'The last admin can''t be removed.';
  end if;
  return old;
end;
$$;
drop trigger if exists admins_keep_one on public.admins;
create trigger admins_keep_one before delete on public.admins
  for each row execute function public.keep_one_admin();
