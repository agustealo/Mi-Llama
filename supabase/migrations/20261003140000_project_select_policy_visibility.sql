begin;

-- public.projects_select_accessible called public.can_access_project(id), which
-- resolves through public.is_project_owner(id) and therefore reads public.projects
-- to decide visibility of the very row being evaluated.
--
-- Row-level security evaluates that expression with the statement snapshot, which
-- predates an INSERT on public.projects. The newly inserted row is invisible to
-- it, so the predicate is false and the insert is rejected even though the caller
-- is the owner. PostgREST hits this on every insert that asks for the created row
-- (Prefer: return=representation), which is how the workspace creates a project,
-- a conversation, and most project content.
--
-- Reading the row's own owner_id column keeps the same authorization meaning
-- without a self-referential table scan: owners still match directly, and
-- membership still resolves through public.project_members, which is a different
-- table and therefore visible within the same statement.

drop policy if exists projects_select_accessible on public.projects;

create policy projects_select_accessible
    on public.projects
    for select
    to authenticated
    using (owner_id = auth.uid() or public.is_project_member(id, null));

commit;