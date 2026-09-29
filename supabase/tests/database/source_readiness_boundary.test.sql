begin;

create extension if not exists pgtap with schema extensions;

select plan(8);

insert into auth.users (id, email, raw_user_meta_data)
values
    ('a1111111-1111-4111-8111-111111111111', 'readiness-owner@example.test', '{}'::jsonb),
    ('a2222222-2222-4222-8222-222222222222', 'readiness-editor@example.test', '{}'::jsonb)
on conflict (id) do nothing;

insert into public.projects (id, owner_id, title)
values (
    'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
    'a1111111-1111-4111-8111-111111111111',
    'Readiness Boundary Project'
);

insert into public.project_members (project_id, user_id, role)
values (
    'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
    'a2222222-2222-4222-8222-222222222222',
    'editor'
);

insert into public.sources (
    id, project_id, created_by, filename, media_type, kind,
    checksum_sha256, size_bytes, status
)
values
    (
        'b1111111-1111-4111-8111-111111111111',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        'a1111111-1111-4111-8111-111111111111',
        'ready.txt', 'text/plain', 'text', repeat('1', 64), 128, 'ready'
    ),
    (
        'b2222222-2222-4222-8222-222222222222',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        'a1111111-1111-4111-8111-111111111111',
        'failed.txt', 'text/plain', 'text', repeat('2', 64), 128, 'failed'
    ),
    (
        'b3333333-3333-4333-8333-333333333333',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        'a1111111-1111-4111-8111-111111111111',
        'processing.txt', 'text/plain', 'text', repeat('3', 64), 128, 'processing'
    );

insert into public.source_versions (
    id, source_id, project_id, created_by, version_number, storage_path,
    checksum_sha256, parser, character_count, status, research_status
)
values
    (
        'c1111111-1111-4111-8111-111111111111',
        'b1111111-1111-4111-8111-111111111111',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        'a1111111-1111-4111-8111-111111111111',
        1,
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa/b1111111-1111-4111-8111-111111111111/c1111111-1111-4111-8111-111111111111/ready.txt',
        repeat('1', 64), 'plain-text', 20, 'ready', 'disabled'
    ),
    (
        'c2222222-2222-4222-8222-222222222222',
        'b2222222-2222-4222-8222-222222222222',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        'a1111111-1111-4111-8111-111111111111',
        1,
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa/b2222222-2222-4222-8222-222222222222/c2222222-2222-4222-8222-222222222222/failed.txt',
        repeat('2', 64), 'plain-text', 20, 'failed', 'not_indexed'
    ),
    (
        'c3333333-3333-4333-8333-333333333333',
        'b3333333-3333-4333-8333-333333333333',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        'a1111111-1111-4111-8111-111111111111',
        1,
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa/b3333333-3333-4333-8333-333333333333/c3333333-3333-4333-8333-333333333333/processing.txt',
        repeat('3', 64), 'plain-text', 20, 'processing', 'not_indexed'
    );

insert into public.source_chunks (
    id, source_version_id, source_id, project_id, ordinal, content,
    character_start, character_end
)
values
    (
        'd1111111-1111-4111-8111-111111111111',
        'c1111111-1111-4111-8111-111111111111',
        'b1111111-1111-4111-8111-111111111111',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        0, 'ready source evidence', 0, 20
    ),
    (
        'd2222222-2222-4222-8222-222222222222',
        'c2222222-2222-4222-8222-222222222222',
        'b2222222-2222-4222-8222-222222222222',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        0, 'failed source residue', 0, 20
    ),
    (
        'd3333333-3333-4333-8333-333333333333',
        'c3333333-3333-4333-8333-333333333333',
        'b3333333-3333-4333-8333-333333333333',
        'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        0, 'processing source data', 0, 22
    );

insert into public.research_claims (id, project_id, created_by, statement)
values (
    'e1111111-1111-4111-8111-111111111111',
    'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
    'a1111111-1111-4111-8111-111111111111',
    'Only ready source material may become claim evidence'
);

set local role authenticated;
set local request.jwt.claim.sub = 'a2222222-2222-4222-8222-222222222222';
set local request.jwt.claim.role = 'authenticated';

select is(
    (select count(*) from public.source_chunks),
    1::bigint,
    'project editor can read only ready source chunks'
);

select is(
    (select count(*) from public.source_chunks where id = 'd2222222-2222-4222-8222-222222222222'),
    0::bigint,
    'failed source chunks are not consumer-readable'
);

select is(
    (select count(*) from public.source_chunks where id = 'd3333333-3333-4333-8333-333333333333'),
    0::bigint,
    'processing source chunks are not consumer-readable'
);

select lives_ok(
    $$
        insert into public.research_notes (project_id, source_chunk_id, body)
        values (
            'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
            'd1111111-1111-4111-8111-111111111111',
            'Ready source note'
        )
    $$,
    'ready source chunk can back a research note'
);

select throws_ok(
    $$
        insert into public.research_notes (project_id, source_chunk_id, body)
        values (
            'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
            'd2222222-2222-4222-8222-222222222222',
            'Invalid failed-source note'
        )
    $$,
    'P0001',
    'research note source chunk must belong to a ready source in the same project',
    'failed source chunk cannot back a research note'
);

select lives_ok(
    $$
        insert into public.claim_evidence (
            project_id, claim_id, source_id, source_version_id, chunk_id, stance
        ) values (
            'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
            'e1111111-1111-4111-8111-111111111111',
            'b1111111-1111-4111-8111-111111111111',
            'c1111111-1111-4111-8111-111111111111',
            'd1111111-1111-4111-8111-111111111111',
            'supports'
        )
    $$,
    'ready source chunk can become claim evidence'
);

select throws_ok(
    $$
        insert into public.claim_evidence (
            project_id, claim_id, source_id, source_version_id, chunk_id, stance
        ) values (
            'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
            'e1111111-1111-4111-8111-111111111111',
            'b2222222-2222-4222-8222-222222222222',
            'c2222222-2222-4222-8222-222222222222',
            'd2222222-2222-4222-8222-222222222222',
            'supports'
        )
    $$,
    'P0001',
    'claim evidence source provenance must reference a ready source',
    'failed source chunk cannot become claim evidence'
);

select throws_ok(
    $$
        insert into public.claim_evidence (
            project_id, claim_id, source_id, source_version_id, chunk_id, stance
        ) values (
            'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
            'e1111111-1111-4111-8111-111111111111',
            'b3333333-3333-4333-8333-333333333333',
            'c3333333-3333-4333-8333-333333333333',
            'd3333333-3333-4333-8333-333333333333',
            'context'
        )
    $$,
    'P0001',
    'claim evidence source provenance must reference a ready source',
    'processing source chunk cannot become claim evidence'
);

select * from finish();
rollback;
