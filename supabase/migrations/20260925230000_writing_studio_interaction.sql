begin;

create table public.manuscript_drafts (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    document_id uuid not null unique references public.manuscript_documents(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    updated_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    base_revision_id uuid references public.manuscript_revisions(id) on delete restrict,
    version bigint not null default 1 check (version > 0),
    editor_state jsonb not null,
    plain_text text not null check (char_length(plain_text) <= 2000000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.writing_proposals (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    document_id uuid not null references public.manuscript_documents(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    base_draft_version bigint not null check (base_draft_version > 0),
    base_revision_id uuid references public.manuscript_revisions(id) on delete restrict,
    operation text not null check (
        operation in ('rewrite', 'improve', 'expand', 'condense', 'continue', 'custom')
    ),
    model text not null check (char_length(btrim(model)) between 1 and 200),
    prompt text check (prompt is null or char_length(prompt) <= 4000),
    selection_start integer not null check (selection_start >= 0),
    selection_end integer not null check (selection_end > selection_start),
    selection_hash text not null check (selection_hash ~ '^[0-9a-f]{64}$'),
    original_text text not null check (
        char_length(original_text) between 1 and 200000
    ),
    proposed_text text not null check (
        char_length(proposed_text) between 1 and 200000
    ),
    context_manifest jsonb not null,
    status text not null default 'proposed'
        check (status in ('proposed', 'accepted', 'rejected', 'stale')),
    reviewed_by uuid references auth.users(id) on delete set null,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_manuscript_drafts_project_updated
    on public.manuscript_drafts(project_id, updated_at desc);
create index idx_writing_proposals_document_created
    on public.writing_proposals(project_id, document_id, created_at desc);
create index idx_writing_proposals_open
    on public.writing_proposals(project_id, document_id, status, created_at desc);

create or replace function public.validate_manuscript_draft()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if not exists (
        select 1
        from public.manuscript_documents document
        where document.id = new.document_id
          and document.project_id = new.project_id
    ) then
        raise exception 'manuscript draft document must belong to the same project';
    end if;

    if new.base_revision_id is not null and not exists (
        select 1
        from public.manuscript_revisions revision
        where revision.id = new.base_revision_id
          and revision.document_id = new.document_id
          and revision.project_id = new.project_id
    ) then
        raise exception 'manuscript draft base revision must belong to the manuscript document';
    end if;

    if tg_op = 'UPDATE' then
        if new.id is distinct from old.id
            or new.project_id is distinct from old.project_id
            or new.document_id is distinct from old.document_id
            or new.created_by is distinct from old.created_by
            or new.created_at is distinct from old.created_at then
            raise exception 'manuscript draft provenance fields are immutable';
        end if;

        if new.version <> old.version + 1 then
            raise exception 'manuscript draft version must advance exactly once';
        end if;
    end if;

    if auth.uid() is null then
        raise exception 'authentication required';
    end if;
    new.updated_by := auth.uid();
    return new;
end;
$$;

create trigger manuscript_drafts_set_updated_at
before update on public.manuscript_drafts
for each row execute function public.set_updated_at();

create trigger manuscript_drafts_validate
before insert or update on public.manuscript_drafts
for each row execute function public.validate_manuscript_draft();

create or replace function public.validate_writing_proposal()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if not exists (
        select 1
        from public.manuscript_documents document
        where document.id = new.document_id
          and document.project_id = new.project_id
    ) then
        raise exception 'writing proposal document must belong to the same project';
    end if;

    if new.base_revision_id is not null and not exists (
        select 1
        from public.manuscript_revisions revision
        where revision.id = new.base_revision_id
          and revision.document_id = new.document_id
          and revision.project_id = new.project_id
    ) then
        raise exception 'writing proposal base revision must belong to the manuscript document';
    end if;

    if tg_op = 'UPDATE' then
        if new.id is distinct from old.id
            or new.project_id is distinct from old.project_id
            or new.document_id is distinct from old.document_id
            or new.created_by is distinct from old.created_by
            or new.base_draft_version is distinct from old.base_draft_version
            or new.base_revision_id is distinct from old.base_revision_id
            or new.operation is distinct from old.operation
            or new.model is distinct from old.model
            or new.prompt is distinct from old.prompt
            or new.selection_start is distinct from old.selection_start
            or new.selection_end is distinct from old.selection_end
            or new.selection_hash is distinct from old.selection_hash
            or new.original_text is distinct from old.original_text
            or new.proposed_text is distinct from old.proposed_text
            or new.context_manifest is distinct from old.context_manifest
            or new.created_at is distinct from old.created_at then
            raise exception 'writing proposal provenance fields are immutable';
        end if;

        if old.status <> 'proposed' or new.status not in ('accepted', 'rejected', 'stale') then
            raise exception 'writing proposal status transition is invalid';
        end if;

        if auth.uid() is null then
            raise exception 'authentication required';
        end if;
        new.reviewed_by := auth.uid();
        new.reviewed_at := now();
    end if;

    return new;
end;
$$;

create trigger writing_proposals_set_updated_at
before update on public.writing_proposals
for each row execute function public.set_updated_at();

create trigger writing_proposals_validate
before insert or update on public.writing_proposals
for each row execute function public.validate_writing_proposal();

alter table public.manuscript_drafts enable row level security;
alter table public.writing_proposals enable row level security;

revoke all on public.manuscript_drafts from anon;
revoke all on public.writing_proposals from anon;
revoke all on public.manuscript_drafts from authenticated;
revoke all on public.writing_proposals from authenticated;

grant select, insert on public.manuscript_drafts to authenticated;
grant update (base_revision_id, version, editor_state, plain_text)
    on public.manuscript_drafts to authenticated;
grant select, insert on public.writing_proposals to authenticated;
grant update (status) on public.writing_proposals to authenticated;

create policy manuscript_drafts_select_project
on public.manuscript_drafts
for select
to authenticated
using (public.can_access_project(project_id));

create policy manuscript_drafts_insert_editor
on public.manuscript_drafts
for insert
to authenticated
with check (
    created_by = auth.uid()
    and updated_by = auth.uid()
    and public.can_edit_project(project_id)
);

create policy manuscript_drafts_update_editor
on public.manuscript_drafts
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy writing_proposals_select_project
on public.writing_proposals
for select
to authenticated
using (public.can_access_project(project_id));

create policy writing_proposals_insert_editor
on public.writing_proposals
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
);

create policy writing_proposals_update_editor
on public.writing_proposals
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create or replace function public.apply_writing_proposal(
    p_project_id uuid,
    p_document_id uuid,
    p_proposal_id uuid,
    p_expected_draft_version bigint,
    p_editor_state jsonb,
    p_plain_text text
)
returns setof public.manuscript_drafts
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    target_draft public.manuscript_drafts%rowtype;
    target_proposal public.writing_proposals%rowtype;
    current_selection text;
    expected_plain_text text;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;

    select *
    into target_draft
    from public.manuscript_drafts draft
    where draft.project_id = p_project_id
      and draft.document_id = p_document_id
    for update;

    if not found then
        raise exception 'manuscript draft not found';
    end if;

    select *
    into target_proposal
    from public.writing_proposals proposal
    where proposal.id = p_proposal_id
      and proposal.project_id = p_project_id
      and proposal.document_id = p_document_id
    for update;

    if not found then
        raise exception 'writing proposal not found';
    end if;
    if target_proposal.status <> 'proposed' then
        raise exception 'writing proposal is stale';
    end if;
    if target_draft.version <> p_expected_draft_version
       or target_proposal.base_draft_version <> p_expected_draft_version then
        raise exception 'writing proposal draft version is stale';
    end if;

    current_selection := substring(
        target_draft.plain_text
        from target_proposal.selection_start + 1
        for target_proposal.selection_end - target_proposal.selection_start
    );
    if current_selection is distinct from target_proposal.original_text then
        raise exception 'writing proposal selection is stale';
    end if;

    expected_plain_text :=
        substring(target_draft.plain_text from 1 for target_proposal.selection_start)
        || target_proposal.proposed_text
        || substring(target_draft.plain_text from target_proposal.selection_end + 1);

    if p_plain_text is distinct from expected_plain_text then
        raise exception 'writing proposal application does not match the reviewed replacement';
    end if;
    if char_length(p_plain_text) > 2000000 then
        raise exception 'manuscript draft exceeds maximum size';
    end if;

    update public.manuscript_drafts
    set editor_state = p_editor_state,
        plain_text = p_plain_text,
        version = target_draft.version + 1,
        updated_by = caller
    where id = target_draft.id
    returning * into target_draft;

    update public.writing_proposals
    set status = 'accepted',
        reviewed_by = caller,
        reviewed_at = now()
    where id = target_proposal.id;

    return next target_draft;
end;
$$;

revoke all on function public.apply_writing_proposal(uuid, uuid, uuid, bigint, jsonb, text)
    from public;
grant execute on function public.apply_writing_proposal(uuid, uuid, uuid, bigint, jsonb, text)
    to authenticated;

commit;
