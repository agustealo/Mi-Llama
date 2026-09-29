begin;

create or replace function public.cleanup_failed_source_ingests_after_ready()
returns trigger
language plpgsql
security definer
set search_path = public, storage
as $$
begin
    if new.status <> 'ready' or old.status = 'ready' then
        return new;
    end if;

    delete from public.sources failed
    where failed.project_id = new.project_id
      and failed.checksum_sha256 = new.checksum_sha256
      and failed.id <> new.id
      and failed.status = 'failed'
      and not exists (
          select 1
          from public.source_versions version
          join storage.objects object
            on object.bucket_id = 'mi-llama-sources'
           and object.name = version.storage_path
          where version.source_id = failed.id
      );

    return new;
end;
$$;

revoke all on function public.cleanup_failed_source_ingests_after_ready() from public;

create trigger sources_cleanup_failed_ingests_after_ready
after update of status on public.sources
for each row
when (new.status = 'ready' and old.status is distinct from new.status)
execute function public.cleanup_failed_source_ingests_after_ready();

commit;
