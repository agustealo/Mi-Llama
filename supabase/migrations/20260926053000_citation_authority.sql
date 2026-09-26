begin;

create table public.source_citation_metadata (
    source_id uuid primary key references public.sources(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    created_by uuid not null default auth.uid(),
    updated_by uuid not null default auth.uid(),
    version bigint not null default 1 check (version > 0),
    csl jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (jsonb_typeof(csl) = 'object'),
    check (char_length(btrim(coalesce(csl ->> 'title', ''))) between 1 and 1000),
    check (char_length(btrim(coalesce(csl ->> 'type', ''))) between 1 and 100)
);

create table public.citation_insertions (
    id uuid primary key,
    project_id uuid not null references public.projects(id) on delete cascade,
    document_id uuid not null references public.manuscript_documents(id) on delete cascade,
    citation_id uuid not null unique references public.citation_candidates(id) on delete restrict,
    source_id uuid not null references public.sources(id) on delete restrict,
    metadata_version bigint not null check (metadata_version > 0),
    style text not null check (style in ('apa-7', 'mla-9', 'chicago-author-date')),
    rendered_citation text not null check (char_length(rendered_citation) between 1 and 1000),
    rendered_bibliography text not null check (char_length(rendered_bibliography) between 1 and 8000),
    revision_id uuid not null references public.manuscript_revisions(id) on delete restrict,
    citation_link_id uuid not null unique references public.writing_research_links(id) on delete restrict,
    character_start integer not null check (character_start >= 0),
    character_end integer not null check (character_end > character_start),
    created_by uuid not null default auth.uid(),
    created_at timestamptz not null default now()
);

create index idx_source_citation_metadata_project
    on public.source_citation_metadata(project_id, updated_at desc);
create index idx_citation_insertions_document
    on public.citation_insertions(project_id, document_id, created_at desc);

create trigger source_citation_metadata_set_updated_at
before update on public.source_citation_metadata
for each row execute function public.set_updated_at();

create or replace function public.validate_source_citation_metadata()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if not exists (
        select 1
        from public.sources source
        where source.id = new.source_id
          and source.project_id = new.project_id
    ) then
        raise exception 'citation metadata source must belong to the same project';
    end if;

    if coalesce(new.csl ->> 'id', '') <> new.source_id::text then
        raise exception 'citation metadata CSL id must match the source';
    end if;

    if octet_length(new.csl::text) > 65536 then
        raise exception 'citation metadata exceeds maximum size';
    end if;

    if tg_op = 'UPDATE' then
        if new.source_id is distinct from old.source_id
            or new.project_id is distinct from old.project_id
            or new.created_by is distinct from old.created_by
            or new.created_at is distinct from old.created_at then
            raise exception 'citation metadata provenance fields are immutable';
        end if;
        if new.version <> old.version + 1 then
            raise exception 'citation metadata version must advance exactly once';
        end if;
    end if;

    if auth.uid() is null then
        raise exception 'authentication required';
    end if;
    new.updated_by := auth.uid();
    return new;
end;
$$;

create trigger source_citation_metadata_validate
before insert or update on public.source_citation_metadata
for each row execute function public.validate_source_citation_metadata();

alter table public.source_citation_metadata enable row level security;
alter table public.citation_insertions enable row level security;

revoke all on public.source_citation_metadata from public;
revoke all on public.source_citation_metadata from anon;
revoke all on public.source_citation_metadata from authenticated;
revoke all on public.citation_insertions from public;
revoke all on public.citation_insertions from anon;
revoke all on public.citation_insertions from authenticated;

grant select on public.source_citation_metadata to authenticated;
grant insert (source_id, project_id, created_by, updated_by, version, csl)
    on public.source_citation_metadata to authenticated;
grant update (version, csl, updated_by)
    on public.source_citation_metadata to authenticated;
grant select on public.citation_insertions to authenticated;

create policy source_citation_metadata_select_project
on public.source_citation_metadata
for select
to authenticated
using (public.can_access_project(project_id));

create policy source_citation_metadata_insert_editor
on public.source_citation_metadata
for insert
to authenticated
with check (
    created_by = auth.uid()
    and updated_by = auth.uid()
    and public.can_edit_project(project_id)
);

create policy source_citation_metadata_update_editor
on public.source_citation_metadata
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy citation_insertions_select_project
on public.citation_insertions
for select
to authenticated
using (public.can_access_project(project_id));

create or replace function public.save_source_citation_metadata(
    p_project_id uuid,
    p_source_id uuid,
    p_expected_version bigint,
    p_csl jsonb
)
returns setof public.source_citation_metadata
language plpgsql
security invoker
set search_path = public
as $$
declare
    caller uuid;
    target public.source_citation_metadata%rowtype;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;
    if not exists (
        select 1
        from public.sources source
        where source.id = p_source_id
          and source.project_id = p_project_id
    ) then
        raise exception 'source not found';
    end if;
    if jsonb_typeof(p_csl) is distinct from 'object'
        or btrim(coalesce(p_csl ->> 'title', '')) = ''
        or btrim(coalesce(p_csl ->> 'type', '')) = '' then
        raise exception 'citation metadata requires CSL type and title';
    end if;
    if coalesce(p_csl ->> 'id', '') <> p_source_id::text then
        raise exception 'citation metadata CSL id must match the source';
    end if;
    if octet_length(p_csl::text) > 65536 then
        raise exception 'citation metadata exceeds maximum size';
    end if;

    select *
    into target
    from public.source_citation_metadata metadata
    where metadata.source_id = p_source_id
      and metadata.project_id = p_project_id
    for update;

    if not found then
        if p_expected_version is not null then
            raise exception 'citation metadata version is stale';
        end if;
        insert into public.source_citation_metadata (
            source_id,
            project_id,
            created_by,
            updated_by,
            version,
            csl
        ) values (
            p_source_id,
            p_project_id,
            caller,
            caller,
            1,
            p_csl
        )
        returning * into target;
    else
        if p_expected_version is null or target.version <> p_expected_version then
            raise exception 'citation metadata version is stale';
        end if;
        update public.source_citation_metadata metadata
        set csl = p_csl,
            version = target.version + 1,
            updated_by = caller
        where metadata.source_id = p_source_id
          and metadata.project_id = p_project_id
        returning * into target;
    end if;

    return next target;
end;
$$;

revoke all on function public.save_source_citation_metadata(uuid, uuid, bigint, jsonb)
    from public;
revoke all on function public.save_source_citation_metadata(uuid, uuid, bigint, jsonb)
    from anon;
grant execute on function public.save_source_citation_metadata(uuid, uuid, bigint, jsonb)
    to authenticated;

create or replace function public.insert_writing_citation(
    p_project_id uuid,
    p_document_id uuid,
    p_citation_id uuid,
    p_insertion_id uuid,
    p_expected_draft_version bigint,
    p_metadata_version bigint,
    p_style text,
    p_rendered_citation text,
    p_rendered_bibliography text
)
returns table(
    draft jsonb,
    revision jsonb,
    citation jsonb,
    citation_link jsonb,
    insertion jsonb
)
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    existing_insertion public.citation_insertions%rowtype;
    target_citation public.citation_candidates%rowtype;
    target_evidence public.claim_evidence%rowtype;
    target_metadata public.source_citation_metadata%rowtype;
    target_draft public.manuscript_drafts%rowtype;
    evidence_link public.writing_research_links%rowtype;
    target_revision public.manuscript_revisions%rowtype;
    inserted_revision public.manuscript_revisions%rowtype;
    inserted_link public.writing_research_links%rowtype;
    inserted_insertion public.citation_insertions%rowtype;
    previous_citation_status text;
    insertion_position integer;
    citation_start integer;
    citation_end integer;
    fragment text;
    next_content text;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;
    if p_style not in ('apa-7', 'mla-9', 'chicago-author-date') then
        raise exception 'citation style is not supported';
    end if;
    if char_length(btrim(p_rendered_citation)) not between 1 and 1000
        or char_length(btrim(p_rendered_bibliography)) not between 1 and 8000 then
        raise exception 'rendered citation payload is invalid';
    end if;

    select *
    into existing_insertion
    from public.citation_insertions item
    where item.id = p_insertion_id
       or item.citation_id = p_citation_id
    order by case when item.id = p_insertion_id then 0 else 1 end
    limit 1;

    if found then
        if existing_insertion.project_id <> p_project_id
            or existing_insertion.document_id <> p_document_id
            or existing_insertion.citation_id <> p_citation_id then
            raise exception 'citation insertion id already belongs to another operation';
        end if;

        select * into target_draft
        from public.manuscript_drafts item
        where item.project_id = p_project_id and item.document_id = p_document_id;
        select * into inserted_revision
        from public.manuscript_revisions item
        where item.id = existing_insertion.revision_id;
        select * into target_citation
        from public.citation_candidates item
        where item.id = existing_insertion.citation_id;
        select * into inserted_link
        from public.writing_research_links item
        where item.id = existing_insertion.citation_link_id;

        return query select
            to_jsonb(target_draft),
            to_jsonb(inserted_revision),
            to_jsonb(target_citation),
            to_jsonb(inserted_link),
            to_jsonb(existing_insertion);
        return;
    end if;

    select *
    into target_citation
    from public.citation_candidates item
    where item.id = p_citation_id
      and item.project_id = p_project_id
    for update;

    if not found then
        raise exception 'citation candidate not found';
    end if;
    if target_citation.status = 'rejected' then
        raise exception 'rejected citation cannot be inserted';
    end if;
    previous_citation_status := target_citation.status;

    select *
    into target_evidence
    from public.claim_evidence item
    where item.id = target_citation.evidence_id
      and item.project_id = p_project_id;
    if not found then
        raise exception 'citation evidence not found';
    end if;

    select *
    into target_metadata
    from public.source_citation_metadata metadata
    where metadata.source_id = target_evidence.source_id
      and metadata.project_id = p_project_id
    for update;
    if not found then
        raise exception 'source citation metadata is required';
    end if;
    if target_metadata.version <> p_metadata_version then
        raise exception 'citation metadata version is stale';
    end if;

    select *
    into target_draft
    from public.manuscript_drafts item
    where item.project_id = p_project_id
      and item.document_id = p_document_id
    for update;
    if not found then
        raise exception 'manuscript draft not found';
    end if;
    if target_draft.version <> p_expected_draft_version then
        raise exception 'manuscript draft version is stale';
    end if;

    select link.*
    into evidence_link
    from public.writing_research_links link
    where link.project_id = p_project_id
      and link.document_id = p_document_id
      and link.kind = 'evidence'
      and link.entity_id = target_evidence.id
      and link.revision_id is not null
      and link.character_start is not null
      and link.character_end is not null
    order by link.created_at desc
    limit 1;
    if not found then
        raise exception 'citation evidence is not linked to this manuscript';
    end if;

    select *
    into target_revision
    from public.manuscript_revisions item
    where item.id = evidence_link.revision_id
      and item.document_id = p_document_id
      and item.project_id = p_project_id;
    if not found then
        raise exception 'citation evidence revision not found';
    end if;

    if target_draft.base_revision_id is distinct from target_revision.id
        or target_draft.plain_text is distinct from target_revision.content then
        raise exception 'manuscript draft changed after the evidence checkpoint';
    end if;

    insertion_position := evidence_link.character_end;
    if insertion_position > evidence_link.character_start
        and substring(target_revision.content from insertion_position for 1) ~ '[.!?]' then
        insertion_position := insertion_position - 1;
    end if;

    fragment := case
        when insertion_position = 0
            or substring(target_revision.content from insertion_position for 1) ~ E'\s'
        then btrim(p_rendered_citation)
        else ' ' || btrim(p_rendered_citation)
    end;
    citation_start := insertion_position + char_length(fragment) - char_length(btrim(p_rendered_citation));
    citation_end := citation_start + char_length(btrim(p_rendered_citation));

    next_content :=
        substring(target_revision.content from 1 for insertion_position)
        || fragment
        || substring(target_revision.content from insertion_position + 1);

    if char_length(next_content) > 2000000 then
        raise exception 'manuscript draft exceeds maximum size';
    end if;

    select created.*
    into inserted_revision
    from public.create_manuscript_revision(
        p_project_id,
        p_document_id,
        next_content
    ) created;
    if not found then
        raise exception 'citation manuscript revision was not created';
    end if;

    update public.manuscript_drafts item
    set base_revision_id = inserted_revision.id,
        plain_text = next_content,
        editor_state = jsonb_build_object('schema', 'plain_text_v1', 'text', next_content),
        version = target_draft.version + 1,
        updated_by = caller
    where item.id = target_draft.id
    returning * into target_draft;

    update public.writing_proposals proposal
    set status = 'stale'
    where proposal.project_id = p_project_id
      and proposal.document_id = p_document_id
      and proposal.status = 'proposed';

    if target_citation.status = 'proposed' then
        update public.citation_candidates item
        set status = 'accepted'
        where item.id = target_citation.id
        returning * into target_citation;
    end if;

    insert into public.writing_research_links (
        project_id,
        document_id,
        revision_id,
        created_by,
        kind,
        entity_id,
        character_start,
        character_end
    ) values (
        p_project_id,
        p_document_id,
        inserted_revision.id,
        caller,
        'citation',
        target_citation.id,
        citation_start,
        citation_end
    )
    returning * into inserted_link;

    insert into public.citation_insertions (
        id,
        project_id,
        document_id,
        citation_id,
        source_id,
        metadata_version,
        style,
        rendered_citation,
        rendered_bibliography,
        revision_id,
        citation_link_id,
        character_start,
        character_end,
        created_by
    ) values (
        p_insertion_id,
        p_project_id,
        p_document_id,
        target_citation.id,
        target_evidence.source_id,
        p_metadata_version,
        p_style,
        btrim(p_rendered_citation),
        btrim(p_rendered_bibliography),
        inserted_revision.id,
        inserted_link.id,
        citation_start,
        citation_end,
        caller
    )
    returning * into inserted_insertion;

    if previous_citation_status = 'proposed' then
        insert into public.learning_signals (
            project_id,
            user_id,
            event_type,
            entity_type,
            entity_id,
            metadata
        ) values (
            p_project_id,
            caller,
            'citation_accepted',
            'citation_candidate',
            target_citation.id,
            jsonb_build_object(
                'claim_id', target_citation.claim_id,
                'evidence_id', target_citation.evidence_id,
                'style', p_style,
                'metadata_version', p_metadata_version
            )
        );

        insert into public.learning_signals (
            project_id,
            user_id,
            event_type,
            entity_type,
            entity_id,
            metadata
        ) values (
            p_project_id,
            caller,
            'source_cited',
            'source_chunk',
            target_evidence.chunk_id,
            jsonb_build_object(
                'claim_id', target_citation.claim_id,
                'citation_id', target_citation.id,
                'style', p_style
            )
        );
    end if;

    return query select
        to_jsonb(target_draft),
        to_jsonb(inserted_revision),
        to_jsonb(target_citation),
        to_jsonb(inserted_link),
        to_jsonb(inserted_insertion);
end;
$$;

revoke all on function public.insert_writing_citation(
    uuid, uuid, uuid, uuid, bigint, bigint, text, text, text
) from public;
revoke all on function public.insert_writing_citation(
    uuid, uuid, uuid, uuid, bigint, bigint, text, text, text
) from anon;
grant execute on function public.insert_writing_citation(
    uuid, uuid, uuid, uuid, bigint, bigint, text, text, text
) to authenticated;

commit;
