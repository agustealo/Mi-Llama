begin;

alter table public.conversations
    add column document_id uuid references public.manuscript_documents(id) on delete cascade;

alter table public.messages
    add column context jsonb;

create index idx_conversations_document_updated
    on public.conversations(project_id, document_id, updated_at desc)
    where document_id is not null;

create or replace function public.validate_document_conversation()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.document_id is not null and not exists (
        select 1
        from public.manuscript_documents document
        where document.id = new.document_id
          and document.project_id = new.project_id
    ) then
        raise exception 'conversation document must belong to the same project';
    end if;

    if tg_op = 'UPDATE' then
        if new.id is distinct from old.id
            or new.project_id is distinct from old.project_id
            or new.document_id is distinct from old.document_id
            or new.created_by is distinct from old.created_by
            or new.created_at is distinct from old.created_at then
            raise exception 'conversation scope and provenance are immutable';
        end if;
    end if;

    return new;
end;
$$;

create trigger conversations_validate_document_scope
before insert or update on public.conversations
for each row execute function public.validate_document_conversation();

revoke update on public.conversations from authenticated;
grant update (title, model) on public.conversations to authenticated;

create or replace function public.validate_message_context()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    parent_conversation public.conversations%rowtype;
    target_draft public.manuscript_drafts%rowtype;
    context_document_id uuid;
    context_base_revision_id uuid;
    context_draft_version bigint;
    context_start integer;
    context_end integer;
    context_excerpt text;
    context_hash text;
    canonical_excerpt text;
begin
    select *
    into parent_conversation
    from public.conversations
    where id = new.conversation_id;

    if not found then
        raise exception 'message conversation not found';
    end if;

    if new.context is null then
        if new.role = 'user' and parent_conversation.document_id is not null then
            raise exception 'document conversation user messages require manuscript context';
        end if;
        return new;
    end if;

    if new.role <> 'user' then
        raise exception 'only user messages may carry manuscript context';
    end if;
    if parent_conversation.document_id is null then
        raise exception 'project conversation messages cannot carry manuscript context';
    end if;
    if jsonb_typeof(new.context) <> 'object'
        or new.context->>'kind' is distinct from 'manuscript_draft' then
        raise exception 'message context must be a manuscript_draft object';
    end if;

    begin
        context_document_id := (new.context->>'document_id')::uuid;
        context_draft_version := (new.context->>'draft_version')::bigint;
        context_start := (new.context->>'character_start')::integer;
        context_end := (new.context->>'character_end')::integer;
        context_base_revision_id := nullif(new.context->>'base_revision_id', '')::uuid;
    exception
        when invalid_text_representation or numeric_value_out_of_range then
            raise exception 'message context contains invalid identifiers or offsets';
    end;

    context_excerpt := new.context->>'excerpt';
    context_hash := new.context->>'sha256';

    if context_document_id is distinct from parent_conversation.document_id then
        raise exception 'message context document does not match conversation';
    end if;
    if context_draft_version is null or context_draft_version < 1 then
        raise exception 'message context draft version is invalid';
    end if;
    if context_start is null or context_end is null
        or context_start < 0 or context_end < context_start then
        raise exception 'message context range is invalid';
    end if;
    if context_end - context_start > 16000 then
        raise exception 'message context exceeds the 16000 character limit';
    end if;
    if context_excerpt is null or context_hash is null
        or context_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'message context excerpt or hash is invalid';
    end if;

    select *
    into target_draft
    from public.manuscript_drafts
    where project_id = parent_conversation.project_id
      and document_id = parent_conversation.document_id;

    if not found then
        raise exception 'message context manuscript draft not found';
    end if;
    if target_draft.version is distinct from context_draft_version then
        raise exception 'message context draft version is stale';
    end if;
    if target_draft.base_revision_id is distinct from context_base_revision_id then
        raise exception 'message context base revision is stale';
    end if;
    if context_end > char_length(target_draft.plain_text) then
        raise exception 'message context range exceeds the manuscript draft';
    end if;

    canonical_excerpt := substring(
        target_draft.plain_text
        from context_start + 1
        for context_end - context_start
    );
    if canonical_excerpt is distinct from context_excerpt then
        raise exception 'message context excerpt does not match the manuscript draft';
    end if;
    if encode(digest(convert_to(context_excerpt, 'UTF8'), 'sha256'), 'hex')
        is distinct from context_hash then
        raise exception 'message context hash does not match the excerpt';
    end if;

    return new;
end;
$$;

create trigger messages_validate_context
before insert on public.messages
for each row execute function public.validate_message_context();

commit;
