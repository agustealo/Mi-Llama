begin;

alter table public.learning_signals
    drop constraint if exists learning_signals_event_type_check;

alter table public.learning_signals
add constraint learning_signals_event_type_check
check (
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
        'research_suggestion_rejected',
        'writing_finding_confirmed',
        'writing_finding_dismissed',
        'writing_gap_created'
    )
);

create table public.writing_analysis_runs (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    document_id uuid not null references public.manuscript_documents(id) on delete cascade,
    revision_id uuid not null references public.manuscript_revisions(id) on delete restrict,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    model text not null check (char_length(btrim(model)) between 1 and 200),
    character_start integer not null check (character_start >= 0),
    character_end integer not null check (character_end > character_start),
    created_at timestamptz not null default now()
);

create table public.writing_analysis_findings (
    id uuid primary key default gen_random_uuid(),
    analysis_id uuid not null references public.writing_analysis_runs(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    document_id uuid not null references public.manuscript_documents(id) on delete cascade,
    revision_id uuid not null references public.manuscript_revisions(id) on delete restrict,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    character_start integer not null check (character_start >= 0),
    character_end integer not null check (character_end > character_start),
    statement text not null check (char_length(btrim(statement)) between 1 and 8000),
    search_query text not null check (char_length(btrim(search_query)) between 1 and 4000),
    assessment text not null check (assessment in ('supported', 'contradicted', 'insufficient')),
    explanation text not null check (char_length(btrim(explanation)) between 1 and 8000),
    status text not null default 'proposed'
        check (status in ('proposed', 'confirmed', 'dismissed', 'research_question_created')),
    research_question_id uuid references public.research_questions(id) on delete restrict,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.writing_finding_candidates (
    id uuid primary key default gen_random_uuid(),
    analysis_id uuid not null references public.writing_analysis_runs(id) on delete cascade,
    finding_id uuid not null references public.writing_analysis_findings(id) on delete cascade,
    project_id uuid not null references public.projects(id) on delete cascade,
    chunk_id uuid not null references public.source_chunks(id) on delete restrict,
    source_id uuid not null references public.sources(id) on delete restrict,
    source_version_id uuid not null references public.source_versions(id) on delete restrict,
    created_by uuid not null default auth.uid() references auth.users(id) on delete cascade,
    rank integer not null check (rank >= 0),
    relevance double precision not null check (relevance >= 0),
    relation text not null check (relation in ('supports', 'contradicts', 'context', 'unclear')),
    created_at timestamptz not null default now(),
    unique (finding_id, chunk_id)
);

create index idx_writing_analysis_runs_document_created
    on public.writing_analysis_runs(project_id, document_id, created_at desc);
create index idx_writing_analysis_findings_analysis_position
    on public.writing_analysis_findings(analysis_id, character_start, created_at);
create index idx_writing_analysis_findings_project_status
    on public.writing_analysis_findings(project_id, status, assessment);
create index idx_writing_finding_candidates_analysis_rank
    on public.writing_finding_candidates(analysis_id, finding_id, rank);

create trigger writing_analysis_findings_set_updated_at
before update on public.writing_analysis_findings
for each row execute function public.set_updated_at();

create or replace function public.validate_writing_analysis_run()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    revision_length integer;
begin
    select char_length(revision.content)
    into revision_length
    from public.manuscript_revisions revision
    where revision.id = new.revision_id
      and revision.document_id = new.document_id
      and revision.project_id = new.project_id;

    if revision_length is null then
        raise exception 'writing analysis revision must belong to the manuscript document';
    end if;

    if new.character_end > revision_length then
        raise exception 'writing analysis range exceeds the manuscript revision';
    end if;

    return new;
end;
$$;

create trigger writing_analysis_runs_validate
before insert on public.writing_analysis_runs
for each row execute function public.validate_writing_analysis_run();

create or replace function public.validate_writing_analysis_finding()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    analysis_row public.writing_analysis_runs%rowtype;
begin
    if tg_op = 'UPDATE' then
        if new.id is distinct from old.id
            or new.analysis_id is distinct from old.analysis_id
            or new.project_id is distinct from old.project_id
            or new.document_id is distinct from old.document_id
            or new.revision_id is distinct from old.revision_id
            or new.created_by is distinct from old.created_by
            or new.character_start is distinct from old.character_start
            or new.character_end is distinct from old.character_end
            or new.statement is distinct from old.statement
            or new.search_query is distinct from old.search_query
            or new.assessment is distinct from old.assessment
            or new.explanation is distinct from old.explanation
            or new.created_at is distinct from old.created_at then
            raise exception 'writing finding analysis provenance is immutable';
        end if;
    end if;

    select *
    into analysis_row
    from public.writing_analysis_runs analysis
    where analysis.id = new.analysis_id;

    if not found
        or analysis_row.project_id <> new.project_id
        or analysis_row.document_id <> new.document_id
        or analysis_row.revision_id <> new.revision_id then
        raise exception 'writing finding must belong to its analysis scope';
    end if;

    if new.character_start < analysis_row.character_start
        or new.character_end > analysis_row.character_end then
        raise exception 'writing finding must remain inside the analyzed passage';
    end if;

    if new.research_question_id is not null and not exists (
        select 1
        from public.research_questions question
        where question.id = new.research_question_id
          and question.project_id = new.project_id
    ) then
        raise exception 'writing finding research question must belong to the same project';
    end if;

    return new;
end;
$$;

create trigger writing_analysis_findings_validate
before insert or update on public.writing_analysis_findings
for each row execute function public.validate_writing_analysis_finding();

create or replace function public.validate_writing_finding_candidate()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if not exists (
        select 1
        from public.writing_analysis_findings finding
        where finding.id = new.finding_id
          and finding.analysis_id = new.analysis_id
          and finding.project_id = new.project_id
    ) then
        raise exception 'writing finding candidate must belong to its analysis finding';
    end if;

    if not exists (
        select 1
        from public.source_chunks chunk
        where chunk.id = new.chunk_id
          and chunk.project_id = new.project_id
          and chunk.source_id = new.source_id
          and chunk.source_version_id = new.source_version_id
    ) then
        raise exception 'writing finding candidate chunk provenance is invalid';
    end if;

    return new;
end;
$$;

create trigger writing_finding_candidates_validate
before insert on public.writing_finding_candidates
for each row execute function public.validate_writing_finding_candidate();

alter table public.writing_analysis_runs enable row level security;
alter table public.writing_analysis_findings enable row level security;
alter table public.writing_finding_candidates enable row level security;

revoke all on public.writing_analysis_runs from anon;
revoke all on public.writing_analysis_findings from anon;
revoke all on public.writing_finding_candidates from anon;
revoke all on public.writing_analysis_runs from authenticated;
revoke all on public.writing_analysis_findings from authenticated;
revoke all on public.writing_finding_candidates from authenticated;

grant select on public.writing_analysis_runs to authenticated;
grant select on public.writing_analysis_findings to authenticated;
grant select on public.writing_finding_candidates to authenticated;

create policy writing_analysis_runs_select_project
on public.writing_analysis_runs
for select
to authenticated
using (public.can_access_project(project_id));

create policy writing_analysis_findings_select_project
on public.writing_analysis_findings
for select
to authenticated
using (public.can_access_project(project_id));

create policy writing_finding_candidates_select_project
on public.writing_finding_candidates
for select
to authenticated
using (public.can_access_project(project_id));

create or replace function public.persist_writing_analysis(
    p_project_id uuid,
    p_document_id uuid,
    p_revision_id uuid,
    p_model text,
    p_character_start integer,
    p_character_end integer,
    p_findings jsonb
)
returns setof public.writing_analysis_runs
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    run_row public.writing_analysis_runs%rowtype;
    finding_data jsonb;
    candidate_data jsonb;
    finding_id uuid;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;
    if jsonb_typeof(p_findings) <> 'array' then
        raise exception 'analysis findings must be a JSON array';
    end if;
    if jsonb_array_length(p_findings) > 20 then
        raise exception 'analysis may contain at most 20 findings';
    end if;

    insert into public.writing_analysis_runs (
        project_id, document_id, revision_id, created_by,
        model, character_start, character_end
    ) values (
        p_project_id, p_document_id, p_revision_id, caller,
        p_model, p_character_start, p_character_end
    )
    returning * into run_row;

    for finding_data in select value from jsonb_array_elements(p_findings)
    loop
        if jsonb_typeof(coalesce(finding_data->'candidates', '[]'::jsonb)) <> 'array' then
            raise exception 'finding candidates must be a JSON array';
        end if;
        if jsonb_array_length(coalesce(finding_data->'candidates', '[]'::jsonb)) > 10 then
            raise exception 'a finding may contain at most 10 evidence candidates';
        end if;

        insert into public.writing_analysis_findings (
            analysis_id, project_id, document_id, revision_id, created_by,
            character_start, character_end, statement, search_query,
            assessment, explanation
        ) values (
            run_row.id, p_project_id, p_document_id, p_revision_id, caller,
            (finding_data->>'character_start')::integer,
            (finding_data->>'character_end')::integer,
            finding_data->>'statement',
            finding_data->>'search_query',
            finding_data->>'assessment',
            finding_data->>'explanation'
        )
        returning id into finding_id;

        for candidate_data in
            select value
            from jsonb_array_elements(coalesce(finding_data->'candidates', '[]'::jsonb))
        loop
            insert into public.writing_finding_candidates (
                analysis_id, finding_id, project_id, chunk_id, source_id,
                source_version_id, created_by, rank, relevance, relation
            ) values (
                run_row.id,
                finding_id,
                p_project_id,
                (candidate_data->>'chunk_id')::uuid,
                (candidate_data->>'source_id')::uuid,
                (candidate_data->>'source_version_id')::uuid,
                caller,
                (candidate_data->>'rank')::integer,
                (candidate_data->>'relevance')::double precision,
                candidate_data->>'relation'
            );
        end loop;
    end loop;

    return next run_row;
end;
$$;

revoke all on function public.persist_writing_analysis(
    uuid, uuid, uuid, text, integer, integer, jsonb
) from public;
grant execute on function public.persist_writing_analysis(
    uuid, uuid, uuid, text, integer, integer, jsonb
) to authenticated;

create or replace function public.review_writing_finding(
    p_project_id uuid,
    p_finding_id uuid,
    p_status text
)
returns setof public.writing_analysis_findings
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    finding_row public.writing_analysis_findings%rowtype;
    signal_event text;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;
    if p_status not in ('confirmed', 'dismissed') then
        raise exception 'writing finding review status is invalid';
    end if;

    select *
    into finding_row
    from public.writing_analysis_findings finding
    where finding.id = p_finding_id
      and finding.project_id = p_project_id
    for update;

    if not found then
        raise exception 'writing finding not found';
    end if;
    if finding_row.status = 'research_question_created' then
        raise exception 'writing finding already became a research question';
    end if;

    update public.writing_analysis_findings
    set status = p_status
    where id = p_finding_id
      and project_id = p_project_id
    returning * into finding_row;

    signal_event := case
        when p_status = 'confirmed' then 'writing_finding_confirmed'
        else 'writing_finding_dismissed'
    end;

    insert into public.learning_signals (
        project_id, user_id, event_type, entity_type, entity_id, metadata
    ) values (
        p_project_id,
        caller,
        signal_event,
        'writing_finding',
        p_finding_id,
        jsonb_build_object('assessment', finding_row.assessment)
    );

    return next finding_row;
end;
$$;

revoke all on function public.review_writing_finding(uuid, uuid, text) from public;
grant execute on function public.review_writing_finding(uuid, uuid, text) to authenticated;

create or replace function public.promote_writing_finding_to_question(
    p_project_id uuid,
    p_finding_id uuid,
    p_priority integer
)
returns setof public.research_questions
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    finding_row public.writing_analysis_findings%rowtype;
    question_row public.research_questions%rowtype;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if not public.can_edit_project(p_project_id) then
        raise exception 'project edit access required';
    end if;
    if p_priority < 1 or p_priority > 5 then
        raise exception 'research question priority must be between 1 and 5';
    end if;

    select *
    into finding_row
    from public.writing_analysis_findings finding
    where finding.id = p_finding_id
      and finding.project_id = p_project_id
    for update;

    if not found then
        raise exception 'writing finding not found';
    end if;
    if finding_row.status = 'dismissed' then
        raise exception 'dismissed writing finding cannot become a research question';
    end if;
    if finding_row.research_question_id is not null then
        raise exception 'writing finding already has a research question';
    end if;

    insert into public.research_questions (
        project_id, created_by, question, priority
    ) values (
        p_project_id,
        caller,
        left(
            'What evidence supports or contradicts this manuscript claim: '
            || finding_row.statement,
            4000
        ),
        p_priority
    )
    returning * into question_row;

    update public.writing_analysis_findings
    set status = 'research_question_created',
        research_question_id = question_row.id
    where id = p_finding_id
      and project_id = p_project_id;

    insert into public.learning_signals (
        project_id, user_id, event_type, entity_type, entity_id, metadata
    ) values (
        p_project_id,
        caller,
        'writing_gap_created',
        'writing_finding',
        p_finding_id,
        jsonb_build_object('research_question_id', question_row.id)
    );

    return next question_row;
end;
$$;

revoke all on function public.promote_writing_finding_to_question(
    uuid, uuid, integer
) from public;
grant execute on function public.promote_writing_finding_to_question(
    uuid, uuid, integer
) to authenticated;

commit;
