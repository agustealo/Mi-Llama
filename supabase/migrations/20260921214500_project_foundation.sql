begin;

create extension if not exists pgcrypto;

create table public.projects (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    description text check (description is null or char_length(description) <= 4000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.project_members (
    project_id uuid not null references public.projects(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('editor', 'researcher', 'reviewer', 'reader')),
    created_at timestamptz not null default now(),
    primary key (project_id, user_id)
);

create table public.conversations (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    title text not null default 'New conversation' check (char_length(title) between 1 and 120),
    model text not null check (char_length(btrim(model)) > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    role text not null check (role in ('system', 'user', 'assistant')),
    content text not null check (char_length(content) > 0),
    created_at timestamptz not null default now()
);

create table public.learning_signals (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    event_type text not null check (
        event_type in (
            'research_result_impression',
            'research_result_opened',
            'research_result_saved',
            'research_result_rejected',
            'source_cited',
            'source_untrusted',
            'citation_accepted',
            'citation_rejected',
            'ai_edit_accepted',
            'ai_edit_rejected',
            'research_suggestion_accepted',
            'research_suggestion_rejected'
        )
    ),
    entity_type text check (entity_type is null or char_length(entity_type) <= 80),
    entity_id uuid,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index idx_project_members_user on public.project_members(user_id, project_id);
create index idx_conversations_project_updated on public.conversations(project_id, updated_at desc);
create index idx_messages_conversation_created on public.messages(conversation_id, created_at);
create index idx_learning_signals_project_created on public.learning_signals(project_id, created_at desc);
create index idx_learning_signals_user_event on public.learning_signals(user_id, event_type, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger projects_set_updated_at
before update on public.projects
for each row execute function public.set_updated_at();

create trigger conversations_set_updated_at
before update on public.conversations
for each row execute function public.set_updated_at();

create or replace function public.is_project_owner(target_project_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.projects p
        where p.id = target_project_id
          and p.owner_id = auth.uid()
    );
$$;

create or replace function public.is_project_member(
    target_project_id uuid,
    allowed_roles text[] default null
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.project_members pm
        where pm.project_id = target_project_id
          and pm.user_id = auth.uid()
          and (allowed_roles is null or pm.role = any(allowed_roles))
    );
$$;

create or replace function public.can_access_project(target_project_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select public.is_project_owner(target_project_id)
        or public.is_project_member(target_project_id, null);
$$;

create or replace function public.can_edit_project(target_project_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select public.is_project_owner(target_project_id)
        or public.is_project_member(target_project_id, array['editor', 'researcher']);
$$;

revoke all on function public.is_project_owner(uuid) from public;
revoke all on function public.is_project_member(uuid, text[]) from public;
revoke all on function public.can_access_project(uuid) from public;
revoke all on function public.can_edit_project(uuid) from public;
grant execute on function public.is_project_owner(uuid) to authenticated;
grant execute on function public.is_project_member(uuid, text[]) to authenticated;
grant execute on function public.can_access_project(uuid) to authenticated;
grant execute on function public.can_edit_project(uuid) to authenticated;

alter table public.projects enable row level security;
alter table public.project_members enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.learning_signals enable row level security;

revoke all on public.projects from anon;
revoke all on public.project_members from anon;
revoke all on public.conversations from anon;
revoke all on public.messages from anon;
revoke all on public.learning_signals from anon;

grant select, insert, update, delete on public.projects to authenticated;
grant select, insert, update, delete on public.project_members to authenticated;
grant select, insert, update, delete on public.conversations to authenticated;
grant select, insert on public.messages to authenticated;
grant select, insert on public.learning_signals to authenticated;

create policy projects_select_accessible
on public.projects
for select
to authenticated
using (public.can_access_project(id));

create policy projects_insert_owned
on public.projects
for insert
to authenticated
with check (owner_id = auth.uid());

create policy projects_update_owned
on public.projects
for update
to authenticated
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

create policy projects_delete_owned
on public.projects
for delete
to authenticated
using (owner_id = auth.uid());

create policy project_members_select_accessible
on public.project_members
for select
to authenticated
using (public.can_access_project(project_id));

create policy project_members_insert_owner
on public.project_members
for insert
to authenticated
with check (public.is_project_owner(project_id));

create policy project_members_update_owner
on public.project_members
for update
to authenticated
using (public.is_project_owner(project_id))
with check (public.is_project_owner(project_id));

create policy project_members_delete_owner
on public.project_members
for delete
to authenticated
using (public.is_project_owner(project_id));

create policy conversations_select_project
on public.conversations
for select
to authenticated
using (public.can_access_project(project_id));

create policy conversations_insert_project_editor
on public.conversations
for insert
to authenticated
with check (
    created_by = auth.uid()
    and public.can_edit_project(project_id)
);

create policy conversations_update_creator_or_owner
on public.conversations
for update
to authenticated
using (created_by = auth.uid() or public.is_project_owner(project_id))
with check (public.can_edit_project(project_id));

create policy conversations_delete_creator_or_owner
on public.conversations
for delete
to authenticated
using (created_by = auth.uid() or public.is_project_owner(project_id));

create policy messages_select_project
on public.messages
for select
to authenticated
using (
    exists (
        select 1
        from public.conversations c
        where c.id = messages.conversation_id
          and public.can_access_project(c.project_id)
    )
);

create policy messages_insert_project_editor
on public.messages
for insert
to authenticated
with check (
    created_by = auth.uid()
    and exists (
        select 1
        from public.conversations c
        where c.id = messages.conversation_id
          and public.can_edit_project(c.project_id)
    )
);

create policy learning_signals_select_own
on public.learning_signals
for select
to authenticated
using (user_id = auth.uid());

create policy learning_signals_insert_own_project
on public.learning_signals
for insert
to authenticated
with check (
    user_id = auth.uid()
    and public.can_access_project(project_id)
);

commit;
