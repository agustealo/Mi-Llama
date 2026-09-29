begin;

create or replace function public.can_cleanup_source_storage_object(object_name text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.source_versions version
        join public.sources source
          on source.id = version.source_id
         and source.project_id = version.project_id
        where version.storage_path = object_name
          and version.project_id = public.source_storage_project_id(object_name)
          and version.status in ('processing', 'failed')
          and source.status in ('processing', 'failed')
          and (
              public.can_edit_project(version.project_id)
              or (
                  version.created_by = auth.uid()
                  and source.created_by = auth.uid()
              )
          )
    );
$$;

revoke execute on function public.can_cleanup_source_storage_object(text) from public;
revoke execute on function public.can_cleanup_source_storage_object(text) from anon;
revoke execute on function public.can_cleanup_source_storage_object(text) from authenticated;
grant execute on function public.can_cleanup_source_storage_object(text) to authenticated;

drop policy if exists mi_llama_sources_select_cleanup_delete on storage.objects;

create policy mi_llama_sources_select_cleanup_delete
on storage.objects
for select
to authenticated
using (
    bucket_id = 'mi-llama-sources'
    and storage.allow_any_operation(
        array['object.delete', 'object.delete_many']
    )
    and public.can_cleanup_source_storage_object(name)
);

drop policy if exists mi_llama_sources_delete_failed_processing on storage.objects;

create policy mi_llama_sources_delete_failed_processing
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'mi-llama-sources'
    and public.can_cleanup_source_storage_object(name)
);

commit;
