begin;

alter table public.manuscript_revisions
add column editor_state jsonb;

update public.manuscript_revisions
set editor_state = jsonb_build_object(
    'schema', 'plain_text_v1',
    'text', content
)
where editor_state is null;

alter table public.manuscript_revisions
alter column editor_state set not null;

alter table public.manuscript_revisions
add constraint manuscript_revisions_editor_state_schema_check
check (
    jsonb_typeof(editor_state) = 'object'
    and editor_state ->> 'schema' in ('plain_text_v1', 'tiptap_v1')
    and (
        editor_state ->> 'schema' <> 'plain_text_v1'
        or editor_state ->> 'text' = content
    )
    and (
        editor_state ->> 'schema' <> 'tiptap_v1'
        or (
            jsonb_typeof(editor_state -> 'doc') = 'object'
            and editor_state -> 'doc' ->> 'type' = 'doc'
        )
    )
);

create or replace function public.populate_manuscript_revision_editor_state()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    snapshot jsonb;
begin
    if new.editor_state is null then
        select draft.editor_state
        into snapshot
        from public.manuscript_drafts draft
        where draft.project_id = new.project_id
          and draft.document_id = new.document_id
          and draft.plain_text = new.content
        limit 1;

        new.editor_state := coalesce(
            snapshot,
            jsonb_build_object('schema', 'plain_text_v1', 'text', new.content)
        );
    end if;

    if jsonb_typeof(new.editor_state) <> 'object'
        or new.editor_state ->> 'schema' not in ('plain_text_v1', 'tiptap_v1') then
        raise exception 'manuscript revision editor state schema is invalid';
    end if;

    if new.editor_state ->> 'schema' = 'plain_text_v1'
        and new.editor_state ->> 'text' is distinct from new.content then
        raise exception 'plain-text revision state must match revision content';
    end if;

    if new.editor_state ->> 'schema' = 'tiptap_v1'
        and (
            jsonb_typeof(new.editor_state -> 'doc') is distinct from 'object'
            or new.editor_state -> 'doc' ->> 'type' is distinct from 'doc'
        ) then
        raise exception 'tiptap revision state requires a document root';
    end if;

    return new;
end;
$$;

revoke all on function public.populate_manuscript_revision_editor_state() from public;
revoke all on function public.populate_manuscript_revision_editor_state() from anon;
revoke all on function public.populate_manuscript_revision_editor_state() from authenticated;

create trigger manuscript_revisions_populate_editor_state
before insert on public.manuscript_revisions
for each row execute function public.populate_manuscript_revision_editor_state();

create or replace function public.sync_revision_editor_state_on_base_advance()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    updated_revision uuid;
begin
    if new.base_revision_id is null
        or new.base_revision_id is not distinct from old.base_revision_id then
        return null;
    end if;

    update public.manuscript_revisions revision
    set editor_state = new.editor_state
    where revision.id = new.base_revision_id
      and revision.project_id = new.project_id
      and revision.document_id = new.document_id
      and revision.content = new.plain_text
    returning revision.id into updated_revision;

    if updated_revision is null then
        raise exception 'draft base revision does not match the committed manuscript snapshot';
    end if;

    return null;
end;
$$;

revoke all on function public.sync_revision_editor_state_on_base_advance() from public;
revoke all on function public.sync_revision_editor_state_on_base_advance() from anon;
revoke all on function public.sync_revision_editor_state_on_base_advance() from authenticated;

create trigger manuscript_drafts_sync_revision_editor_state
after update of base_revision_id on public.manuscript_drafts
for each row
when (new.base_revision_id is distinct from old.base_revision_id)
execute function public.sync_revision_editor_state_on_base_advance();

commit;
