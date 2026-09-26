begin;

create or replace function public.checkpoint_manuscript_draft(
    p_project_id uuid,
    p_document_id uuid,
    p_expected_draft_version bigint
)
returns setof public.manuscript_revisions
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    target_document public.manuscript_documents%rowtype;
    target_draft public.manuscript_drafts%rowtype;
    inserted_revision public.manuscript_revisions%rowtype;
    next_revision integer;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
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

    select *
    into target_draft
    from public.manuscript_drafts draft
    where draft.project_id = p_project_id
      and draft.document_id = p_document_id
    for update;

    if not found then
        raise exception 'manuscript draft not found';
    end if;
    if target_draft.version <> p_expected_draft_version then
        raise exception 'manuscript draft version is stale';
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
        target_draft.plain_text,
        public.count_manuscript_words(target_draft.plain_text)
    )
    returning * into inserted_revision;

    update public.manuscript_documents
    set current_revision_id = inserted_revision.id,
        current_word_count = inserted_revision.word_count
    where id = p_document_id
      and project_id = p_project_id;

    update public.manuscript_drafts
    set base_revision_id = inserted_revision.id,
        version = target_draft.version + 1,
        updated_by = caller
    where id = target_draft.id;

    update public.writing_proposals
    set status = 'stale'
    where project_id = p_project_id
      and document_id = p_document_id
      and status = 'proposed'
      and base_draft_version <= target_draft.version;

    return next inserted_revision;
end;
$$;

revoke all on function public.checkpoint_manuscript_draft(uuid, uuid, bigint) from public;
grant execute on function public.checkpoint_manuscript_draft(uuid, uuid, bigint)
    to authenticated;

commit;
