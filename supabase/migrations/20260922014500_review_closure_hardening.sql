begin;

-- Contributor IDs are historical provenance, not ownership. Inserts remain
-- constrained to auth.uid() by RLS or security-definer RPCs, but deleting an
-- auth account must not delete shared project content authored by that user.
alter table public.conversations
    drop constraint if exists conversations_created_by_fkey;
alter table public.messages
    drop constraint if exists messages_created_by_fkey;
alter table public.sources
    drop constraint if exists sources_created_by_fkey;
alter table public.source_versions
    drop constraint if exists source_versions_created_by_fkey;
alter table public.research_questions
    drop constraint if exists research_questions_created_by_fkey;
alter table public.research_claims
    drop constraint if exists research_claims_created_by_fkey;
alter table public.research_notes
    drop constraint if exists research_notes_created_by_fkey;
alter table public.claim_evidence
    drop constraint if exists claim_evidence_created_by_fkey;
alter table public.citation_candidates
    drop constraint if exists citation_candidates_created_by_fkey;
alter table public.outline_nodes
    drop constraint if exists outline_nodes_created_by_fkey;
alter table public.manuscript_documents
    drop constraint if exists manuscript_documents_created_by_fkey;
alter table public.manuscript_revisions
    drop constraint if exists manuscript_revisions_created_by_fkey;
alter table public.writing_research_links
    drop constraint if exists writing_research_links_created_by_fkey;
alter table public.writing_analysis_runs
    drop constraint if exists writing_analysis_runs_created_by_fkey;
alter table public.writing_analysis_findings
    drop constraint if exists writing_analysis_findings_created_by_fkey;
alter table public.writing_finding_candidates
    drop constraint if exists writing_finding_candidates_created_by_fkey;

comment on column public.conversations.created_by is
    'Immutable historical author UUID retained even if the auth account is deleted.';
comment on column public.messages.created_by is
    'Immutable historical author UUID retained even if the auth account is deleted.';

-- Conversation ordering follows real activity, not only conversation creation.
create or replace function public.touch_conversation_activity()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    update public.conversations
    set updated_at = now()
    where id = new.conversation_id;
    return new;
end;
$$;

revoke all on function public.touch_conversation_activity() from public;

drop trigger if exists messages_touch_conversation_activity on public.messages;
create trigger messages_touch_conversation_activity
after insert on public.messages
for each row execute function public.touch_conversation_activity();

-- Streaming model turns need a durable cross-worker lease. Local process locks
-- prevent duplicate work in one worker; this table closes the multi-worker race.
create table if not exists public.conversation_reply_leases (
    conversation_id uuid primary key references public.conversations(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    lease_token uuid not null,
    acquired_by uuid not null,
    acquired_at timestamptz not null default now(),
    expires_at timestamptz not null,
    check (expires_at > acquired_at)
);

create index if not exists idx_conversation_reply_leases_expiry
    on public.conversation_reply_leases(expires_at);

alter table public.conversation_reply_leases enable row level security;
revoke all on public.conversation_reply_leases from anon;
revoke all on public.conversation_reply_leases from authenticated;

create or replace function public.acquire_conversation_reply_lease(
    p_conversation_id uuid,
    p_ttl_seconds integer
)
returns table(lease_token uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    target_project_id uuid;
    issued_token uuid;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if p_ttl_seconds < 30 or p_ttl_seconds > 1800 then
        raise exception 'conversation reply lease TTL must be between 30 and 1800 seconds';
    end if;

    select conversation.project_id
    into target_project_id
    from public.conversations conversation
    where conversation.id = p_conversation_id;

    if not found then
        raise exception 'conversation not found';
    end if;
    if not public.can_edit_project(target_project_id) then
        raise exception 'project edit access required';
    end if;

    issued_token := gen_random_uuid();

    insert into public.conversation_reply_leases as existing (
        conversation_id,
        project_id,
        lease_token,
        acquired_by,
        acquired_at,
        expires_at
    ) values (
        p_conversation_id,
        target_project_id,
        issued_token,
        caller,
        now(),
        now() + make_interval(secs => p_ttl_seconds)
    )
    on conflict (conversation_id) do update
    set project_id = excluded.project_id,
        lease_token = excluded.lease_token,
        acquired_by = excluded.acquired_by,
        acquired_at = excluded.acquired_at,
        expires_at = excluded.expires_at
    where existing.expires_at <= now()
    returning existing.lease_token into issued_token;

    if not found then
        raise exception 'conversation reply already in progress';
    end if;

    return query select issued_token;
end;
$$;

revoke all on function public.acquire_conversation_reply_lease(uuid, integer) from public;
grant execute on function public.acquire_conversation_reply_lease(uuid, integer) to authenticated;

create or replace function public.release_conversation_reply_lease(
    p_conversation_id uuid,
    p_lease_token uuid
)
returns table(released boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    deleted_count integer;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;

    delete from public.conversation_reply_leases lease
    where lease.conversation_id = p_conversation_id
      and lease.lease_token = p_lease_token
      and lease.acquired_by = caller;

    get diagnostics deleted_count = row_count;
    return query select deleted_count = 1;
end;
$$;

revoke all on function public.release_conversation_reply_lease(uuid, uuid) from public;
grant execute on function public.release_conversation_reply_lease(uuid, uuid) to authenticated;

-- Serialize hierarchy mutations per project so two concurrent reparents cannot
-- each validate against stale state and commit a cycle.
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

    perform pg_advisory_xact_lock(
        hashtextextended('mi-llama:outline:' || new.project_id::text, 0)
    );

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

-- Once an accepted citation is anchored into writing, later rejection would
-- make a durable manuscript link violate its own acceptance invariant.
create or replace function public.preserve_linked_citation_acceptance()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if old.status = 'accepted'
        and new.status <> 'accepted'
        and exists (
            select 1
            from public.writing_research_links link
            where link.kind = 'citation'
              and link.entity_id = old.id
        ) then
        raise exception 'citation is linked to manuscript writing and must remain accepted';
    end if;
    return new;
end;
$$;

drop trigger if exists citation_candidates_preserve_linked_acceptance
    on public.citation_candidates;
create trigger citation_candidates_preserve_linked_acceptance
before update of status on public.citation_candidates
for each row execute function public.preserve_linked_citation_acceptance();

-- Return the inserted revision and the matching document snapshot from the same
-- transaction. The inner revision function row-locks the document until this
-- outer RPC has read the updated row.
create or replace function public.create_manuscript_revision_result(
    p_project_id uuid,
    p_document_id uuid,
    p_content text
)
returns table(document jsonb, revision jsonb)
language plpgsql
security definer
set search_path = public
as $$
declare
    inserted_revision public.manuscript_revisions%rowtype;
    updated_document public.manuscript_documents%rowtype;
begin
    select created_revision.*
    into inserted_revision
    from public.create_manuscript_revision(
        p_project_id,
        p_document_id,
        p_content
    ) created_revision;

    if not found then
        raise exception 'manuscript revision was not created';
    end if;

    select manuscript.*
    into updated_document
    from public.manuscript_documents manuscript
    where manuscript.id = p_document_id
      and manuscript.project_id = p_project_id;

    if not found then
        raise exception 'manuscript document not found after revision creation';
    end if;

    return query
    select to_jsonb(updated_document), to_jsonb(inserted_revision);
end;
$$;

revoke all on function public.create_manuscript_revision_result(uuid, uuid, text) from public;
grant execute on function public.create_manuscript_revision_result(uuid, uuid, text)
    to authenticated;

commit;
