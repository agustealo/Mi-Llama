begin;

create table public.provenance_dispositions (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    document_id uuid not null references public.manuscript_documents(id) on delete cascade,
    accepted_proposal_id uuid not null references public.writing_proposals(id) on delete restrict,
    disposition text not null check (
        disposition in ('retired', 'superseded', 'needs_regrounding')
    ),
    draft_version bigint not null check (draft_version > 0),
    superseding_proposal_id uuid references public.writing_proposals(id) on delete restrict,
    reason text check (reason is null or char_length(reason) <= 1000),
    created_by uuid not null default auth.uid() references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    check (
        (disposition = 'superseded' and superseding_proposal_id is not null)
        or (disposition <> 'superseded' and superseding_proposal_id is null)
    )
);

create index idx_provenance_dispositions_document_created
    on public.provenance_dispositions(project_id, document_id, created_at desc, id desc);
create index idx_provenance_dispositions_proposal_created
    on public.provenance_dispositions(accepted_proposal_id, created_at desc, id desc);
create unique index idx_provenance_dispositions_idempotent
    on public.provenance_dispositions(
        accepted_proposal_id,
        draft_version,
        disposition,
        coalesce(superseding_proposal_id, '00000000-0000-0000-0000-000000000000'::uuid)
    );

create or replace function public.validate_provenance_disposition()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    current_version bigint;
    target_proposal public.writing_proposals%rowtype;
    replacement public.writing_proposals%rowtype;
begin
    if auth.uid() is null then
        raise exception 'authentication required';
    end if;

    if not public.can_edit_project(new.project_id) then
        raise exception 'project edit access required';
    end if;

    select version into current_version
    from public.manuscript_drafts
    where project_id = new.project_id
      and document_id = new.document_id;

    if current_version is null then
        raise exception 'manuscript draft not found';
    end if;
    if current_version <> new.draft_version then
        raise exception 'draft version conflict';
    end if;

    select * into target_proposal
    from public.writing_proposals
    where id = new.accepted_proposal_id
      and project_id = new.project_id
      and document_id = new.document_id;

    if target_proposal.id is null then
        raise exception 'accepted proposal must belong to the manuscript document';
    end if;
    if target_proposal.status <> 'accepted' then
        raise exception 'provenance disposition requires an accepted proposal';
    end if;
    if jsonb_typeof(target_proposal.context_manifest->'grounding') <> 'object'
        or jsonb_typeof(target_proposal.context_manifest->'grounding'->'citations') <> 'array'
        or jsonb_array_length(target_proposal.context_manifest->'grounding'->'citations') = 0 then
        raise exception 'provenance disposition requires a grounded proposal';
    end if;

    if new.disposition = 'superseded' then
        if new.superseding_proposal_id = new.accepted_proposal_id then
            raise exception 'a proposal cannot supersede itself';
        end if;
        select * into replacement
        from public.writing_proposals
        where id = new.superseding_proposal_id
          and project_id = new.project_id
          and document_id = new.document_id;
        if replacement.id is null then
            raise exception 'superseding proposal must belong to the manuscript document';
        end if;
        if replacement.status <> 'accepted' then
            raise exception 'superseding proposal must be accepted';
        end if;
        if jsonb_typeof(replacement.context_manifest->'grounding') <> 'object'
            or jsonb_typeof(replacement.context_manifest->'grounding'->'citations') <> 'array'
            or jsonb_array_length(replacement.context_manifest->'grounding'->'citations') = 0 then
            raise exception 'superseding proposal must be grounded';
        end if;
        if replacement.base_draft_version <= target_proposal.base_draft_version then
            raise exception 'superseding proposal must target a later manuscript draft';
        end if;
        if coalesce(replacement.reviewed_at, replacement.updated_at, replacement.created_at)
            <= coalesce(target_proposal.reviewed_at, target_proposal.updated_at, target_proposal.created_at) then
            raise exception 'superseding proposal must be accepted after the historical proposal';
        end if;
    end if;

    new.created_by := auth.uid();
    return new;
end;
$$;

create trigger provenance_dispositions_validate
before insert on public.provenance_dispositions
for each row execute function public.validate_provenance_disposition();

alter table public.provenance_dispositions enable row level security;
revoke all on public.provenance_dispositions from anon;
revoke all on public.provenance_dispositions from authenticated;
grant select, insert on public.provenance_dispositions to authenticated;

create policy provenance_dispositions_select_project
on public.provenance_dispositions
for select
to authenticated
using (public.can_access_project(project_id));

create policy provenance_dispositions_insert_editor
on public.provenance_dispositions
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
);

commit;
