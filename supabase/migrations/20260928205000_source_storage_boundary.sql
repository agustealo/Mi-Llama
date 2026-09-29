begin;

drop policy if exists mi_llama_sources_insert_project_editor on storage.objects;

create policy mi_llama_sources_insert_project_editor
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'mi-llama-sources'
    and public.can_edit_project(public.source_storage_project_id(name))
    and exists (
        select 1
        from public.source_versions v
        join public.sources s
          on s.id = v.source_id
         and s.project_id = v.project_id
        where v.storage_path = storage.objects.name
          and v.project_id = public.source_storage_project_id(storage.objects.name)
          and v.status = 'processing'
          and s.status = 'processing'
    )
);

commit;
