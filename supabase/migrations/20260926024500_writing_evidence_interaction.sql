begin;

create or replace function public.promote_writing_evidence(
    p_project_id uuid,
    p_document_id uuid,
    p_promotion_id uuid,
    p_revision_id uuid,
    p_expected_draft_version bigint,
    p_selection_start integer,
    p_selection_end integer,
    p_chunk_id uuid,
    p_stance text,
    p_note text
)
returns table (
    draft jsonb,
    revision jsonb,
    claim jsonb,
    evidence jsonb,
    citation jsonb,
    claim_link jsonb,
    evidence_link jsonb
)
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    target_draft public.manuscript_drafts%rowtype;
    target_revision public.manuscript_revisions%rowtype;
    target_chunk public.source_chunks%rowtype;
    target_claim public.research_claims%rowtype;
    target_evidence public.claim_evidence%rowtype;
    target_citation public.citation_candidates%rowtype;
    target_claim_link public.writing_research_links%rowtype;
    target_evidence_link public.writing_research_links%rowtype;
    selected_text text;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;
    if p_expected_draft_version < 1 then
        raise exception 'draft version must be positive';
    end if;
    if p_selection_start < 0 or p_selection_end <= p_selection_start then
        raise exception 'selection range is invalid';
    end if;
    if p_stance not in ('supports', 'contradicts', 'context') then
        raise exception 'evidence stance is invalid';
    end if;
    if p_note is not null and char_length(p_note) > 8000 then
        raise exception 'evidence note exceeds maximum size';
    end if;

    perform 1
    from public.manuscript_documents document
    where document.id = p_document_id
      and document.project_id = p_project_id
    for update;
    if not found then
        raise exception 'manuscript document not found';
    end if;

    select *
    into target_draft
    from public.manuscript_drafts draft_row
    where draft_row.project_id = p_project_id
      and draft_row.document_id = p_document_id
    for update;
    if not found then
        raise exception 'manuscript draft not found';
    end if;
    if target_draft.version <> p_expected_draft_version then
        raise exception 'manuscript draft version is stale';
    end if;
    if target_draft.base_revision_id is distinct from p_revision_id then
        raise exception 'revision is not the current draft base';
    end if;

    select *
    into target_revision
    from public.manuscript_revisions revision_row
    where revision_row.id = p_revision_id
      and revision_row.project_id = p_project_id
      and revision_row.document_id = p_document_id;
    if not found then
        raise exception 'manuscript revision not found';
    end if;
    if target_revision.content is distinct from target_draft.plain_text then
        raise exception 'revision no longer matches the current draft base';
    end if;
    if p_selection_end > char_length(target_revision.content) then
        raise exception 'selection exceeds manuscript passage';
    end if;

    selected_text := substring(
        target_revision.content
        from p_selection_start + 1
        for p_selection_end - p_selection_start
    );
    if char_length(btrim(selected_text)) < 3 then
        raise exception 'selected passage is too short to promote as a claim';
    end if;
    if char_length(selected_text) > 8000 then
        raise exception 'selected passage exceeds maximum claim size';
    end if;

    select *
    into target_chunk
    from public.source_chunks chunk_row
    where chunk_row.id = p_chunk_id
      and chunk_row.project_id = p_project_id;
    if not found then
        raise exception 'source chunk not found';
    end if;

    insert into public.research_claims (
        id,
        project_id,
        created_by,
        statement
    ) values (
        p_promotion_id,
        p_project_id,
        caller,
        selected_text
    )
    on conflict (id) do nothing;

    select *
    into target_claim
    from public.research_claims claim_row
    where claim_row.id = p_promotion_id
      and claim_row.project_id = p_project_id
      and claim_row.created_by = caller
      and claim_row.statement = selected_text;
    if not found then
        raise exception 'promotion id already belongs to another operation';
    end if;

    insert into public.claim_evidence (
        project_id,
        claim_id,
        source_id,
        source_version_id,
        chunk_id,
        created_by,
        stance,
        note
    ) values (
        p_project_id,
        target_claim.id,
        target_chunk.source_id,
        target_chunk.source_version_id,
        target_chunk.id,
        caller,
        p_stance,
        p_note
    )
    on conflict (claim_id, chunk_id, stance) do nothing;

    select *
    into target_evidence
    from public.claim_evidence evidence_row
    where evidence_row.claim_id = target_claim.id
      and evidence_row.chunk_id = target_chunk.id
      and evidence_row.stance = p_stance;
    if not found then
        raise exception 'claim evidence could not be materialized';
    end if;

    select *
    into target_claim
    from public.research_claims claim_row
    where claim_row.id = target_claim.id;

    select *
    into target_citation
    from public.citation_candidates citation_row
    where citation_row.evidence_id = target_evidence.id;
    if not found then
        raise exception 'citation candidate could not be materialized';
    end if;

    select *
    into target_claim_link
    from public.writing_research_links link_row
    where link_row.project_id = p_project_id
      and link_row.document_id = p_document_id
      and link_row.revision_id = p_revision_id
      and link_row.kind = 'claim'
      and link_row.entity_id = target_claim.id
      and link_row.character_start = p_selection_start
      and link_row.character_end = p_selection_end
    order by link_row.created_at
    limit 1;

    if not found then
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
            p_revision_id,
            caller,
            'claim',
            target_claim.id,
            p_selection_start,
            p_selection_end
        )
        returning * into target_claim_link;
    end if;

    select *
    into target_evidence_link
    from public.writing_research_links link_row
    where link_row.project_id = p_project_id
      and link_row.document_id = p_document_id
      and link_row.revision_id = p_revision_id
      and link_row.kind = 'evidence'
      and link_row.entity_id = target_evidence.id
      and link_row.character_start = p_selection_start
      and link_row.character_end = p_selection_end
    order by link_row.created_at
    limit 1;

    if not found then
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
            p_revision_id,
            caller,
            'evidence',
            target_evidence.id,
            p_selection_start,
            p_selection_end
        )
        returning * into target_evidence_link;
    end if;

    return query
    select
        to_jsonb(target_draft),
        to_jsonb(target_revision),
        to_jsonb(target_claim),
        to_jsonb(target_evidence),
        to_jsonb(target_citation),
        to_jsonb(target_claim_link),
        to_jsonb(target_evidence_link);
end;
$$;

revoke all on function public.promote_writing_evidence(
    uuid, uuid, uuid, uuid, bigint, integer, integer, uuid, text, text
) from public;
grant execute on function public.promote_writing_evidence(
    uuid, uuid, uuid, uuid, bigint, integer, integer, uuid, text, text
) to authenticated;

commit;
