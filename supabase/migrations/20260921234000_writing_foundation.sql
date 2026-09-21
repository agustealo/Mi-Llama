begin;

create table public.outline_nodes (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    parent_id uuid references public.outline_nodes(id) on delete restrict,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    kind text not null check (kind in ('part', 'chapter', 'section')),
    title text not null check (char_length(btrim(title)) between 1 and 300),
    summary text check (summary is null or char_length(summary) <= 8000),
    status text not null default 'planned'
        check (status in ('planned', 'drafting', 'complete', 'archived')),
    position integer not null default 0 check (position >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (parent_id is null or parent_id <> id)
);

create table public.manuscript_documents (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    outline_node_id uuid references public.outline_nodes(id) on delete restrict,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    title text not null check (char_length(btrim(title)) between 1 and 300),
    status text not null default 'drafting'
        check (status in ('drafting', 'review', 'complete', 'archived')),
    current_revision_id uuid,
    current_word_count integer not null default 0 check (current_word_count >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.manuscript_revisions (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references public.manuscript_documents(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    revision_number integer not null check (revision_number > 0),
    created_by uuid not null references auth.users(id) on delete cascade,
    content text not null check (char_length(content) <= 2000000),
    word_count integer not null check (word_count >= 0),
    created_at timestamptz not null default now(),
    unique (document_id, revision_number)
);

alter table public.manuscript_documents
add constraint manuscript_documents_current_revision_fk
foreign key (current_revision_id)
references public.manuscript_revisions(id)
on delete restrict
deferrable initially deferred;

create table public.writing_research_links (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    document_id uuid not null references public.manuscript_documents(id) on delete cascade,
    outline_node_id uuid references public.outline_nodes(id) on delete restrict,
    revision_id uuid references public.manuscript_revisions(id) on delete restrict,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    kind text not null check (kind in ('claim', 'evidence', 'citation')),
    entity_id uuid not null,
    character_start integer check (character_start is null or character_start >= 0),
    character_end integer check (character_end is null or character_end > 0),
    created_at timestamptz not null default now(),
    check (
        (character_start is null and character_end is null)
        or (
            character_start is not null
            and character_end is not null
            and character_end > character_start
        )
    ),
    check (
        revision_id is not null
        or (character_start is null and character_end is null)
    )
);

create index idx_outline_nodes_project_parent_position
    on public.outline_nodes(project_id, parent_id, position, created_at);
create index idx_manuscript_documents_project_updated
    on public.manuscript_documents(project_id, updated_at desc);
create index idx_manuscript_documents_outline
    on public.manuscript_documents(project_id, outline_node_id);
create index idx_manuscript_revisions_document_number
    on public.manuscript_revisions(document_id, revision_number desc);
create index idx_writing_research_links_document
    on public.writing_research_links(project_id, document_id, created_at);
create index idx_writing_research_links_entity
    on public.writing_research_links(project_id, kind, entity_id);

create trigger outline_nodes_set_updated_at
before update on public.outline_nodes
for each row execute function public.set_updated_at();

create trigger manuscript_documents_set_updated_at
before update on public.manuscript_documents
for each row execute function public.set_updated_at();

create or replace function public.validate_outline_node()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    cycle_found boolean;
begin
    if tg_op = 'UPDATE' then
        if new.id is distinct from old.id
            or new.project_id is distinct from old.project_id
            or new.created_by is distinct from old.created_by
            or new.created_at is distinct from old.created_at then
            raise exception 'outline provenance fields are immutable';
        end if;
    end if;

    if new.parent_id is null then
        return new;
    end if;

    if not exists (
        select 1
        from public.outline_nodes parent
        where parent.id = new.parent_id
          and parent.project_id = new.project_id
    ) then
        raise exception 'outline parent must belong to the same project';
    end if;

    with recursive ancestors as (
        select parent.id, parent.parent_id
        from public.outline_nodes parent
        where parent.id = new.parent_id
        union all
        select next_parent.id, next_parent.parent_id
        from public.outline_nodes next_parent
        join ancestors a on next_parent.id = a.parent_id
    )
    select exists (
        select 1
        from ancestors
        where id = new.id
    ) into cycle_found;

    if cycle_found then
        raise exception 'outline hierarchy cannot contain cycles';
    end if;

    return new;
end;
$$;

create trigger outline_nodes_validate
before insert or update on public.outline_nodes
for each row execute function public.validate_outline_node();

create or replace function public.validate_manuscript_document()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if tg_op = 'UPDATE' then
        if new.id is distinct from old.id
            or new.project_id is distinct from old.project_id
            or new.created_by is distinct from old.created_by
            or new.created_at is distinct from old.created_at then
            raise exception 'manuscript provenance fields are immutable';
        end if;
    end if;

    if new.outline_node_id is not null and not exists (
        select 1
        from public.outline_nodes node
        where node.id = new.outline_node_id
          and node.project_id = new.project_id
    ) then
        raise exception 'manuscript outline node must belong to the same project';
    end if;

    return new;
end;
$$;

create trigger manuscript_documents_validate
before insert or update on public.manuscript_documents
for each row execute function public.validate_manuscript_document();

create or replace function public.count_manuscript_words(body text)
returns integer
language sql
immutable
strict
set search_path = public
as $$
    select case
        when btrim(body) = '' then 0
        else cardinality(regexp_split_to_array(btrim(body), E'\\s+'))
    end;
$$;

revoke all on function public.count_manuscript_words(text) from public;
grant execute on function public.count_manuscript_words(text) to authenticated;

create or replace function public.create_manuscript_revision(
    p_project_id uuid,
    p_document_id uuid,
    p_content text
)
returns setof public.manuscript_revisions
language plpgsql
security definer
set search_path = public
as $$
declare
    target_document public.manuscript_documents%rowtype;
    next_revision integer;
    inserted_revision public.manuscript_revisions%rowtype;
    caller uuid;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;

    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;

    if char_length(p_content) > 2000000 then
        raise exception 'manuscript revision exceeds maximum size';
    end if;

    select *
    into target_document
    from public.manuscript_documents document
    where document.id = p_document_id
      and document.project_id = p_project_id
    for update;

    if not found then
        raise exception 'manuscript document not found';
    end if;

    select coalesce(max(revision.revision_number), 0) + 1
    into next_revision
    from public.manuscript_revisions revision
    where revision.document_id = p_document_id;

    insert into public.manuscript_revisions (
        document_id,
        project_id,
        revision_number,
        created_by,
        content,
        word_count
    ) values (
        p_document_id,
        p_project_id,
        next_revision,
        caller,
        p_content,
        public.count_manuscript_words(p_content)
    )
    returning * into inserted_revision;

    update public.manuscript_documents
    set current_revision_id = inserted_revision.id,
        current_word_count = inserted_revision.word_count
    where id = p_document_id
      and project_id = p_project_id;

    return next inserted_revision;
end;
$$;

revoke all on function public.create_manuscript_revision(uuid, uuid, text) from public;
grant execute on function public.create_manuscript_revision(uuid, uuid, text) to authenticated;

create or replace function public.validate_writing_research_link()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    revision_content_length integer;
begin
    if not exists (
        select 1
        from public.manuscript_documents document
        where document.id = new.document_id
          and document.project_id = new.project_id
    ) then
        raise exception 'writing research link document must belong to the same project';
    end if;

    if new.outline_node_id is not null and not exists (
        select 1
        from public.outline_nodes node
        where node.id = new.outline_node_id
          and node.project_id = new.project_id
    ) then
        raise exception 'writing research link outline node must belong to the same project';
    end if;

    if new.revision_id is not null then
        select char_length(revision.content)
        into revision_content_length
        from public.manuscript_revisions revision
        where revision.id = new.revision_id
          and revision.document_id = new.document_id
          and revision.project_id = new.project_id;

        if revision_content_length is null then
            raise exception 'writing research link revision must belong to the manuscript document';
        end if;

        if new.character_end is not null and new.character_end > revision_content_length then
            raise exception 'writing research link passage exceeds revision content';
        end if;
    end if;

    if new.kind = 'claim' then
        if not exists (
            select 1
            from public.research_claims claim
            where claim.id = new.entity_id
              and claim.project_id = new.project_id
        ) then
            raise exception 'linked claim must belong to the same project';
        end if;
    elsif new.kind = 'evidence' then
        if not exists (
            select 1
            from public.claim_evidence evidence
            where evidence.id = new.entity_id
              and evidence.project_id = new.project_id
        ) then
            raise exception 'linked evidence must belong to the same project';
        end if;
    elsif new.kind = 'citation' then
        if not exists (
            select 1
            from public.citation_candidates citation
            where citation.id = new.entity_id
              and citation.project_id = new.project_id
              and citation.status = 'accepted'
        ) then
            raise exception 'linked citation must be accepted and belong to the same project';
        end if;
    end if;

    return new;
end;
$$;

create trigger writing_research_links_validate
before insert on public.writing_research_links
for each row execute function public.validate_writing_research_link();

alter table public.outline_nodes enable row level security;
alter table public.manuscript_documents enable row level security;
alter table public.manuscript_revisions enable row level security;
alter table public.writing_research_links enable row level security;

revoke all on public.outline_nodes from anon;
revoke all on public.manuscript_documents from anon;
revoke all on public.manuscript_revisions from anon;
revoke all on public.writing_research_links from anon;

revoke all on public.outline_nodes from authenticated;
revoke all on public.manuscript_documents from authenticated;
revoke all on public.manuscript_revisions from authenticated;
revoke all on public.writing_research_links from authenticated;

grant select, insert on public.outline_nodes to authenticated;
grant update (parent_id, kind, title, summary, status, position)
    on public.outline_nodes to authenticated;

grant select, insert on public.manuscript_documents to authenticated;
grant update (outline_node_id, title, status)
    on public.manuscript_documents to authenticated;

grant select on public.manuscript_revisions to authenticated;
grant select, insert on public.writing_research_links to authenticated;

create policy outline_nodes_select_project
on public.outline_nodes
for select
to authenticated
using (public.can_access_project(project_id));

create policy outline_nodes_insert_editor
on public.outline_nodes
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
);

create policy outline_nodes_update_editor
on public.outline_nodes
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy manuscript_documents_select_project
on public.manuscript_documents
for select
to authenticated
using (public.can_access_project(project_id));

create policy manuscript_documents_insert_editor
on public.manuscript_documents
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
);

create policy manuscript_documents_update_editor
on public.manuscript_documents
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy manuscript_revisions_select_project
on public.manuscript_revisions
for select
to authenticated
using (public.can_access_project(project_id));

create policy writing_research_links_select_project
on public.writing_research_links
for select
to authenticated
using (public.can_access_project(project_id));

create policy writing_research_links_insert_editor
on public.writing_research_links
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
);

commit;
