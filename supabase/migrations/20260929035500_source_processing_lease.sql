begin;

create or replace function public.enforce_source_status_terminal()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if old.status in ('ready', 'failed') and new.status <> old.status then
        raise exception 'source terminal status cannot transition from % to %', old.status, new.status;
    end if;
    return new;
end;
$$;

create trigger sources_enforce_terminal_status
before update of status on public.sources
for each row
execute function public.enforce_source_status_terminal();

create or replace function public.expire_stale_source_ingests_before_insert()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    stale_message constant text := 'Source processing lease expired';
begin
    -- This trigger intentionally runs with the caller's privileges. RLS remains
    -- authoritative, so an insert attempt cannot expire work in a project the
    -- caller is not allowed to edit.
    update public.source_versions version
    set status = 'failed',
        error_message = stale_message
    where version.status = 'processing'
      and exists (
          select 1
          from public.sources source
          where source.id = version.source_id
            and source.project_id = new.project_id
            and source.checksum_sha256 = new.checksum_sha256
            and source.status = 'processing'
            and source.updated_at <= now() - interval '30 minutes'
      );

    update public.sources source
    set status = 'failed',
        error_message = stale_message
    where source.project_id = new.project_id
      and source.checksum_sha256 = new.checksum_sha256
      and source.status = 'processing'
      and source.updated_at <= now() - interval '30 minutes';

    return new;
end;
$$;

create trigger sources_expire_stale_ingests_before_insert
before insert on public.sources
for each row
execute function public.expire_stale_source_ingests_before_insert();

commit;
