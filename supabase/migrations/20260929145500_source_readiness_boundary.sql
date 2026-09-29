begin;

-- Source chunks exist before an ingest is committed ready. They are an internal
-- staging artifact until both the source and source version become ready, so
-- normal authenticated reads must not expose processing or failed residue.
drop policy if exists source_chunks_select_project on public.source_chunks;
drop policy if exists source_chunks_select_ready_project on public.source_chunks;

create policy source_chunks_select_ready_project
on public.source_chunks
for select
to authenticated
using (
    public.can_access_project(project_id)
    and exists (
        select 1
        from public.source_versions version
        join public.sources source
          on source.id = version.source_id
         and source.project_id = version.project_id
        where version.id = source_chunks.source_version_id
          and version.source_id = source_chunks.source_id
          and version.project_id = source_chunks.project_id
          and version.status = 'ready'
          and source.status = 'ready'
    )
);

create or replace function public.validate_research_note_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.question_id is not null and not exists (
        select 1
        from public.research_questions question
        where question.id = new.question_id
          and question.project_id = new.project_id
    ) then
        raise exception 'research note question must belong to the same project';
    end if;

    if new.source_chunk_id is not null and not exists (
        select 1
        from public.source_chunks chunk
        join public.source_versions version
          on version.id = chunk.source_version_id
         and version.source_id = chunk.source_id
         and version.project_id = chunk.project_id
        join public.sources source
          on source.id = chunk.source_id
         and source.project_id = chunk.project_id
        where chunk.id = new.source_chunk_id
          and chunk.project_id = new.project_id
          and version.status = 'ready'
          and source.status = 'ready'
    ) then
        raise exception 'research note source chunk must belong to a ready source in the same project';
    end if;

    return new;
end;
$$;

create or replace function public.validate_claim_evidence_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if not exists (
        select 1
        from public.research_claims claim
        where claim.id = new.claim_id
          and claim.project_id = new.project_id
    ) then
        raise exception 'claim evidence claim must belong to the same project';
    end if;

    if not exists (
        select 1
        from public.source_chunks chunk
        join public.source_versions version
          on version.id = chunk.source_version_id
         and version.source_id = chunk.source_id
         and version.project_id = chunk.project_id
        join public.sources source
          on source.id = chunk.source_id
         and source.project_id = chunk.project_id
        where chunk.id = new.chunk_id
          and chunk.source_id = new.source_id
          and chunk.source_version_id = new.source_version_id
          and chunk.project_id = new.project_id
          and version.status = 'ready'
          and source.status = 'ready'
    ) then
        raise exception 'claim evidence source provenance must reference a ready source';
    end if;

    return new;
end;
$$;

commit;
