begin;

create or replace function public.validate_manuscript_draft()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    new_schema text;
    old_schema text;
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

    if jsonb_typeof(new.editor_state) is distinct from 'object' then
        raise exception 'manuscript editor state must be an object';
    end if;
    new_schema := new.editor_state ->> 'schema';
    if new_schema not in ('plain_text_v1', 'tiptap_v1') then
        raise exception 'manuscript editor state schema is unsupported';
    end if;
    if new_schema = 'plain_text_v1'
        and coalesce(new.editor_state ->> 'text', '') is distinct from new.plain_text then
        raise exception 'plain-text editor state must match manuscript plain text';
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

        old_schema := old.editor_state ->> 'schema';
        if old_schema is distinct from new_schema
            and old.plain_text is distinct from new.plain_text then
            raise exception 'editor schema migration must preserve canonical manuscript text';
        end if;
    end if;

    if auth.uid() is null then
        raise exception 'authentication required';
    end if;
    new.updated_by := auth.uid();
    return new;
end;
$$;

commit;
