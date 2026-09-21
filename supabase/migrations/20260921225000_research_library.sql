begin;

create table public.sources (
    id uuid primary key,
    project_id uuid not null references public.projects(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    filename text not null check (char_length(btrim(filename)) between 1 and 240),
    media_type text not null check (char_length(btrim(media_type)) between 1 and 200),
    kind text not null check (kind in ('pdf', 'docx', 'epub', 'text', 'markdown', 'html')),
    checksum_sha256 text not null check (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint not null check (size_bytes > 0),
    status text not null default 'processing' check (status in ('processing', 'ready', 'failed')),
    error_message text check (error_message is null or char_length(error_message) <= 1000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.source_versions (
    id uuid primary key,
    source_id uuid not null references public.sources(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    version_number integer not null default 1 check (version_number > 0),
    storage_path text not null unique check (char_length(storage_path) between 1 and 1024),
    checksum_sha256 text not null check (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    parser text not null check (char_length(btrim(parser)) between 1 and 120),
    character_count integer not null check (character_count > 0),
    status text not null default 'processing' check (status in ('processing', 'ready', 'failed')),
    error_message text check (error_message is null or char_length(error_message) <= 1000),
    research_status text not null default 'not_indexed'
        check (research_status in ('not_indexed', 'indexing', 'ready', 'failed', 'disabled')),
    research_error text check (research_error is null or char_length(research_error) <= 1000),
    created_at timestamptz not null default now(),
    unique (source_id, version_number)
);

create table public.source_chunks (
    id uuid primary key,
    source_version_id uuid not null references public.source_versions(id) on delete cascade,
    source_id uuid not null references public.sources(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    ordinal integer not null check (ordinal >= 0),
    location text check (location is null or char_length(location) <= 500),
    content text not null check (char_length(content) > 0),
    character_start integer not null check (character_start >= 0),
    character_end integer not null check (character_end > character_start),
    created_at timestamptz not null default now(),
    unique (source_version_id, ordinal)
);

create index idx_sources_project_updated on public.sources(project_id, updated_at desc);
create index idx_sources_project_checksum on public.sources(project_id, checksum_sha256);
create unique index idx_sources_ready_checksum_unique
    on public.sources(project_id, checksum_sha256)
    where status = 'ready';
create index idx_source_versions_source_version
    on public.source_versions(source_id, version_number desc);
create index idx_source_versions_project_research
    on public.source_versions(project_id, research_status, created_at desc);
create index idx_source_chunks_version_ordinal
    on public.source_chunks(source_version_id, ordinal);
create index idx_source_chunks_project_source
    on public.source_chunks(project_id, source_id);

create trigger sources_set_updated_at
before update on public.sources
for each row execute function public.set_updated_at();

create or replace function public.enforce_source_provenance()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.id is distinct from old.id
        or new.project_id is distinct from old.project_id
        or new.created_by is distinct from old.created_by
        or new.filename is distinct from old.filename
        or new.media_type is distinct from old.media_type
        or new.kind is distinct from old.kind
        or new.checksum_sha256 is distinct from old.checksum_sha256
        or new.size_bytes is distinct from old.size_bytes
        or new.created_at is distinct from old.created_at then
        raise exception 'source provenance fields are immutable';
    end if;
    return new;
end;
$$;

create trigger sources_preserve_provenance
before update on public.sources
for each row execute function public.enforce_source_provenance();

create or replace function public.enforce_source_version_provenance()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.id is distinct from old.id
        or new.source_id is distinct from old.source_id
        or new.project_id is distinct from old.project_id
        or new.created_by is distinct from old.created_by
        or new.version_number is distinct from old.version_number
        or new.storage_path is distinct from old.storage_path
        or new.checksum_sha256 is distinct from old.checksum_sha256
        or new.parser is distinct from old.parser
        or new.character_count is distinct from old.character_count
        or new.created_at is distinct from old.created_at then
        raise exception 'source version provenance fields are immutable';
    end if;
    return new;
end;
$$;

create trigger source_versions_preserve_provenance
before update on public.source_versions
for each row execute function public.enforce_source_version_provenance();

create or replace function public.source_storage_project_id(object_name text)
returns uuid
language plpgsql
immutable
strict
set search_path = public
as $$
declare
    candidate text;
begin
    candidate := split_part(object_name, '/', 1);
    if candidate ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' then
        return candidate::uuid;
    end if;
    return null;
end;
$$;

revoke all on function public.source_storage_project_id(text) from public;
grant execute on function public.source_storage_project_id(text) to authenticated;

alter table public.sources enable row level security;
alter table public.source_versions enable row level security;
alter table public.source_chunks enable row level security;

revoke all on public.sources from anon;
revoke all on public.source_versions from anon;
revoke all on public.source_chunks from anon;

grant select, insert, update on public.sources to authenticated;
grant select, insert, update on public.source_versions to authenticated;
grant select, insert on public.source_chunks to authenticated;

create policy sources_select_project
on public.sources
for select
to authenticated
using (public.can_access_project(project_id));

create policy sources_insert_project_editor
on public.sources
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
);

create policy sources_update_project_editor
on public.sources
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy source_versions_select_project
on public.source_versions
for select
to authenticated
using (public.can_access_project(project_id));

create policy source_versions_insert_project_editor
on public.source_versions
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
    and exists (
        select 1
        from public.sources s
        where s.id = source_versions.source_id
          and s.project_id = source_versions.project_id
          and s.status = 'processing'
    )
);

create policy source_versions_update_project_editor
on public.source_versions
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy source_chunks_select_project
on public.source_chunks
for select
to authenticated
using (public.can_access_project(project_id));

create policy source_chunks_insert_processing_version
on public.source_chunks
for insert
to authenticated
with check (
    public.can_edit_project(project_id)
    and exists (
        select 1
        from public.source_versions v
        where v.id = source_chunks.source_version_id
          and v.source_id = source_chunks.source_id
          and v.project_id = source_chunks.project_id
          and v.status = 'processing'
    )
);

insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values (
    'mi-llama-sources',
    'mi-llama-sources',
    false,
    26214400,
    array[
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/epub+zip',
        'text/plain',
        'text/markdown',
        'text/x-markdown',
        'text/html',
        'application/xhtml+xml',
        'application/octet-stream'
    ]::text[]
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create policy mi_llama_sources_select_project
on storage.objects
for select
to authenticated
using (
    bucket_id = 'mi-llama-sources'
    and public.can_access_project(public.source_storage_project_id(name))
);

create policy mi_llama_sources_insert_project_editor
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'mi-llama-sources'
    and public.can_edit_project(public.source_storage_project_id(name))
);

create policy mi_llama_sources_delete_failed_processing
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'mi-llama-sources'
    and public.can_edit_project(public.source_storage_project_id(name))
    and exists (
        select 1
        from public.source_versions v
        where v.storage_path = storage.objects.name
          and v.status in ('processing', 'failed')
    )
);

commit;
