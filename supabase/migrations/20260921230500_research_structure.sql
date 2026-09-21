begin;

create table public.research_questions (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    question text not null check (char_length(btrim(question)) between 3 and 4000),
    status text not null default 'open'
        check (status in ('open', 'investigating', 'resolved', 'parked')),
    priority smallint not null default 3 check (priority between 1 and 5),
    resolution text check (resolution is null or char_length(resolution) <= 8000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (status <> 'resolved' or char_length(btrim(coalesce(resolution, ''))) > 0)
);

create table public.research_claims (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    statement text not null check (char_length(btrim(statement)) between 3 and 8000),
    status text not null default 'needs_evidence'
        check (status in ('needs_evidence', 'supported', 'disputed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.research_notes (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    question_id uuid references public.research_questions(id) on delete set null,
    source_chunk_id uuid references public.source_chunks(id) on delete set null,
    kind text not null default 'note' check (kind in ('note', 'quote', 'idea', 'summary')),
    title text check (title is null or char_length(title) <= 240),
    body text not null check (char_length(body) between 1 and 40000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.claim_evidence (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    claim_id uuid not null references public.research_claims(id) on delete cascade,
    source_id uuid not null references public.sources(id) on delete cascade,
    source_version_id uuid not null references public.source_versions(id) on delete cascade,
    chunk_id uuid not null references public.source_chunks(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    stance text not null check (stance in ('supports', 'contradicts', 'context')),
    note text check (note is null or char_length(note) <= 8000),
    created_at timestamptz not null default now(),
    unique (claim_id, chunk_id, stance)
);

create table public.citation_candidates (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    claim_id uuid not null references public.research_claims(id) on delete cascade,
    evidence_id uuid not null unique references public.claim_evidence(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    status text not null default 'proposed'
        check (status in ('proposed', 'accepted', 'rejected')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_research_questions_project_status
    on public.research_questions(project_id, status, priority desc, created_at);
create index idx_research_claims_project_status
    on public.research_claims(project_id, status, created_at);
create index idx_research_notes_project_created
    on public.research_notes(project_id, created_at desc);
create index idx_research_notes_question
    on public.research_notes(question_id, created_at desc)
    where question_id is not null;
create index idx_claim_evidence_claim_created
    on public.claim_evidence(claim_id, created_at);
create index idx_claim_evidence_chunk
    on public.claim_evidence(chunk_id, claim_id);
create index idx_citation_candidates_project_status
    on public.citation_candidates(project_id, status, created_at);

create trigger research_questions_set_updated_at
before update on public.research_questions
for each row execute function public.set_updated_at();

create trigger research_claims_set_updated_at
before update on public.research_claims
for each row execute function public.set_updated_at();

create trigger research_notes_set_updated_at
before update on public.research_notes
for each row execute function public.set_updated_at();

create trigger citation_candidates_set_updated_at
before update on public.citation_candidates
for each row execute function public.set_updated_at();

create or replace function public.enforce_research_identity()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.id is distinct from old.id
        or new.project_id is distinct from old.project_id
        or new.created_by is distinct from old.created_by
        or new.created_at is distinct from old.created_at then
        raise exception 'research identity fields are immutable';
    end if;
    return new;
end;
$$;

create trigger research_questions_preserve_identity
before update on public.research_questions
for each row execute function public.enforce_research_identity();

create trigger research_claims_preserve_identity
before update on public.research_claims
for each row execute function public.enforce_research_identity();

create trigger research_notes_preserve_identity
before update on public.research_notes
for each row execute function public.enforce_research_identity();

create trigger citation_candidates_preserve_identity
before update on public.citation_candidates
for each row execute function public.enforce_research_identity();

create or replace function public.validate_research_note_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.question_id is not null and not exists (
        select 1
        from public.research_questions q
        where q.id = new.question_id and q.project_id = new.project_id
    ) then
        raise exception 'research note question must belong to the same project';
    end if;

    if new.source_chunk_id is not null and not exists (
        select 1
        from public.source_chunks c
        where c.id = new.source_chunk_id and c.project_id = new.project_id
    ) then
        raise exception 'research note source chunk must belong to the same project';
    end if;
    return new;
end;
$$;

create trigger research_notes_validate_links
before insert or update on public.research_notes
for each row execute function public.validate_research_note_links();

create or replace function public.validate_claim_evidence_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if not exists (
        select 1
        from public.research_claims c
        where c.id = new.claim_id and c.project_id = new.project_id
    ) then
        raise exception 'claim evidence claim must belong to the same project';
    end if;

    if not exists (
        select 1
        from public.source_chunks c
        where c.id = new.chunk_id
          and c.source_id = new.source_id
          and c.source_version_id = new.source_version_id
          and c.project_id = new.project_id
    ) then
        raise exception 'claim evidence source provenance is inconsistent';
    end if;
    return new;
end;
$$;

create trigger claim_evidence_validate_links
before insert on public.claim_evidence
for each row execute function public.validate_claim_evidence_links();

create or replace function public.preserve_claim_evidence_provenance()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception 'claim evidence is immutable; replace the relation instead';
end;
$$;

create trigger claim_evidence_immutable
before update on public.claim_evidence
for each row execute function public.preserve_claim_evidence_provenance();

create or replace function public.validate_citation_candidate_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if not exists (
        select 1
        from public.claim_evidence e
        where e.id = new.evidence_id
          and e.claim_id = new.claim_id
          and e.project_id = new.project_id
    ) then
        raise exception 'citation candidate must reference evidence from the same claim and project';
    end if;
    return new;
end;
$$;

create trigger citation_candidates_validate_links
before insert on public.citation_candidates
for each row execute function public.validate_citation_candidate_links();

alter table public.research_questions enable row level security;
alter table public.research_claims enable row level security;
alter table public.research_notes enable row level security;
alter table public.claim_evidence enable row level security;
alter table public.citation_candidates enable row level security;

revoke all on public.research_questions from anon;
revoke all on public.research_claims from anon;
revoke all on public.research_notes from anon;
revoke all on public.claim_evidence from anon;
revoke all on public.citation_candidates from anon;

grant select, insert, update on public.research_questions to authenticated;
grant select, insert, update on public.research_claims to authenticated;
grant select, insert, update on public.research_notes to authenticated;
grant select, insert on public.claim_evidence to authenticated;
grant select, insert, update on public.citation_candidates to authenticated;

create policy research_questions_select_project
on public.research_questions
for select
to authenticated
using (public.can_access_project(project_id));

create policy research_questions_insert_editor
on public.research_questions
for insert
to authenticated
with check (created_by = auth.uid() and public.can_edit_project(project_id));

create policy research_questions_update_editor
on public.research_questions
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy research_claims_select_project
on public.research_claims
for select
to authenticated
using (public.can_access_project(project_id));

create policy research_claims_insert_editor
on public.research_claims
for insert
to authenticated
with check (created_by = auth.uid() and public.can_edit_project(project_id));

create policy research_claims_update_editor
on public.research_claims
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy research_notes_select_project
on public.research_notes
for select
to authenticated
using (public.can_access_project(project_id));

create policy research_notes_insert_editor
on public.research_notes
for insert
to authenticated
with check (created_by = auth.uid() and public.can_edit_project(project_id));

create policy research_notes_update_editor
on public.research_notes
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

create policy claim_evidence_select_project
on public.claim_evidence
for select
to authenticated
using (public.can_access_project(project_id));

create policy claim_evidence_insert_editor
on public.claim_evidence
for insert
to authenticated
with check (created_by = auth.uid() and public.can_edit_project(project_id));

create policy citation_candidates_select_project
on public.citation_candidates
for select
to authenticated
using (public.can_access_project(project_id));

create policy citation_candidates_insert_editor
on public.citation_candidates
for insert
to authenticated
with check (created_by = auth.uid() and public.can_edit_project(project_id));

create policy citation_candidates_update_editor
on public.citation_candidates
for update
to authenticated
using (public.can_edit_project(project_id))
with check (public.can_edit_project(project_id));

commit;
