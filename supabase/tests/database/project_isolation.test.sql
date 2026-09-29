begin;

create extension if not exists pgtap with schema extensions;

select plan(24);

insert into auth.users (id, email, raw_user_meta_data)
values
    ('11111111-1111-4111-8111-111111111111', 'owner-a@example.test', '{}'::jsonb),
    ('22222222-2222-4222-8222-222222222222', 'owner-b@example.test', '{}'::jsonb)
on conflict (id) do nothing;

insert into public.projects (id, owner_id, title)
values
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '11111111-1111-4111-8111-111111111111', 'Project A'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '22222222-2222-4222-8222-222222222222', 'Project B');

insert into public.sources (
    id, project_id, created_by, filename, media_type, kind,
    checksum_sha256, size_bytes, status, created_at, updated_at
)
values
    (
        '33333333-3333-4333-8333-333333333333',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '11111111-1111-4111-8111-111111111111',
        'a-ready.txt', 'text/plain', 'text', repeat('a', 64), 128, 'ready', now(), now()
    ),
    (
        '66666666-6666-4666-8666-666666666666',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '11111111-1111-4111-8111-111111111111',
        'a-stale.txt', 'text/plain', 'text', repeat('c', 64), 128, 'processing',
        now() - interval '31 minutes', now() - interval '31 minutes'
    ),
    (
        '88888888-8888-4888-8888-888888888888',
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        '22222222-2222-4222-8222-222222222222',
        'b-processing.txt', 'text/plain', 'text', repeat('b', 64), 128, 'processing', now(), now()
    );

insert into public.source_versions (
    id, source_id, project_id, created_by, version_number, storage_path,
    checksum_sha256, parser, character_count, status, research_status, created_at
)
values
    (
        '44444444-4444-4444-8444-444444444444',
        '33333333-3333-4333-8333-333333333333',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '11111111-1111-4111-8111-111111111111',
        1,
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/33333333-3333-4333-8333-333333333333/44444444-4444-4444-8444-444444444444/a-ready.txt',
        repeat('a', 64), 'plain-text', 128, 'ready', 'disabled', now()
    ),
    (
        '77777777-7777-4777-8777-777777777777',
        '66666666-6666-4666-8666-666666666666',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '11111111-1111-4111-8111-111111111111',
        1,
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/66666666-6666-4666-8666-666666666666/77777777-7777-4777-8777-777777777777/a-stale.txt',
        repeat('c', 64), 'plain-text', 128, 'processing', 'not_indexed', now() - interval '31 minutes'
    ),
    (
        '99999999-9999-4999-8999-999999999999',
        '88888888-8888-4888-8888-888888888888',
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        '22222222-2222-4222-8222-222222222222',
        1,
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/88888888-8888-4888-8888-888888888888/99999999-9999-4999-8999-999999999999/b-processing.txt',
        repeat('b', 64), 'plain-text', 128, 'processing', 'not_indexed', now()
    );

insert into public.source_chunks (
    id, source_version_id, source_id, project_id, ordinal, content,
    character_start, character_end
)
values (
    '55555555-5555-4555-8555-555555555555',
    '44444444-4444-4444-8444-444444444444',
    '33333333-3333-4333-8333-333333333333',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    0, 'Project A evidence', 0, 18
);

insert into public.research_claims (id, project_id, created_by, statement)
values
    (
        'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '11111111-1111-4111-8111-111111111111',
        'Project A claim'
    ),
    (
        'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        '22222222-2222-4222-8222-222222222222',
        'Project B claim'
    );

insert into public.claim_evidence (
    id, project_id, claim_id, source_id, source_version_id, chunk_id,
    created_by, stance
)
values (
    'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    '33333333-3333-4333-8333-333333333333',
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    '11111111-1111-4111-8111-111111111111',
    'supports'
);

insert into public.manuscript_documents (id, project_id, created_by, title)
values
    (
        'ffffffff-ffff-4fff-8fff-ffffffffffff',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '11111111-1111-4111-8111-111111111111',
        'Project A manuscript'
    ),
    (
        '12121212-1212-4212-8212-121212121212',
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        '22222222-2222-4222-8222-222222222222',
        'Project B manuscript'
    );

insert into public.writing_research_links (
    id, project_id, document_id, created_by, kind, entity_id
)
values (
    '13131313-1313-4313-8313-131313131313',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'ffffffff-ffff-4fff-8fff-ffffffffffff',
    '11111111-1111-4111-8111-111111111111',
    'claim',
    'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
);

insert into storage.objects (bucket_id, name)
values (
    'mi-llama-sources',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/33333333-3333-4333-8333-333333333333/44444444-4444-4444-8444-444444444444/a-ready.txt'
);

select results_eq(
    $$
        select c.relname::text
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relname in (
              'projects', 'sources', 'source_versions', 'source_chunks',
              'research_claims', 'claim_evidence', 'citation_candidates',
              'manuscript_documents', 'writing_research_links'
          )
          and c.relrowsecurity
        order by c.relname
    $$,
    array[
        'citation_candidates', 'claim_evidence', 'manuscript_documents',
        'projects', 'research_claims', 'source_chunks', 'source_versions',
        'sources', 'writing_research_links'
    ]::text[],
    'all project-scoped consumer tables under test have RLS enabled'
);

set local role authenticated;
set local request.jwt.claim.sub = '22222222-2222-4222-8222-222222222222';

select results_eq(
    $$select id from public.projects order by id$$,
    array['bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'::uuid],
    'user B sees only project B'
);

select is_empty(
    $$select id from public.projects where id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'$$,
    'user B cannot read project A by guessed project id'
);
select is_empty(
    $$select id from public.sources where id = '33333333-3333-4333-8333-333333333333'$$,
    'user B cannot read project A source by guessed source id'
);
select is_empty(
    $$select id from public.source_versions where id = '44444444-4444-4444-8444-444444444444'$$,
    'user B cannot read project A source version by guessed id'
);
select is_empty(
    $$select id from public.source_chunks where id = '55555555-5555-4555-8555-555555555555'$$,
    'user B cannot read project A source chunk by guessed id'
);
select is_empty(
    $$select id from public.research_claims where id = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'$$,
    'user B cannot read project A claim by guessed id'
);
select is_empty(
    $$select id from public.citation_candidates where claim_id = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'$$,
    'user B cannot read project A citation candidates'
);
select is_empty(
    $$select id from public.manuscript_documents where id = 'ffffffff-ffff-4fff-8fff-ffffffffffff'$$,
    'user B cannot read project A manuscript by guessed id'
);
select is_empty(
    $$select id from public.writing_research_links where id = '13131313-1313-4313-8313-131313131313'$$,
    'user B cannot read project A writing-research link'
);

select is_empty(
    $$
        update public.sources
        set error_message = 'cross-project mutation'
        where id = '33333333-3333-4333-8333-333333333333'
        returning id
    $$,
    'user B cannot update project A source'
);

select throws_ok(
    $$
        insert into public.sources (
            id, project_id, filename, media_type, kind, checksum_sha256, size_bytes
        ) values (
            '14141414-1414-4414-8414-141414141414',
            'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
            'recovery-attack.txt', 'text/plain', 'text', repeat('c', 64), 128
        )
    $$,
    '42501',
    null,
    'user B cannot trigger source recovery inside project A'
);

select is_empty(
    $$
        select name
        from storage.objects
        where bucket_id = 'mi-llama-sources'
          and name = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/33333333-3333-4333-8333-333333333333/44444444-4444-4444-8444-444444444444/a-ready.txt'
    $$,
    'user B cannot read project A storage object'
);

select throws_ok(
    $$
        insert into storage.objects (bucket_id, name)
        values (
            'mi-llama-sources',
            'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/66666666-6666-4666-8666-666666666666/77777777-7777-4777-8777-777777777777/a-stale.txt'
        )
    $$,
    '42501',
    null,
    'user B cannot upload into project A storage path'
);

select results_eq(
    $$
        insert into storage.objects (bucket_id, name)
        values (
            'mi-llama-sources',
            'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/88888888-8888-4888-8888-888888888888/99999999-9999-4999-8999-999999999999/b-processing.txt'
        )
        returning name
    $$,
    array[
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/88888888-8888-4888-8888-888888888888/99999999-9999-4999-8999-999999999999/b-processing.txt'
    ]::text[],
    'user B can upload only a canonically registered project B processing object'
);

select throws_ok(
    $$
        insert into public.claim_evidence (
            project_id, claim_id, source_id, source_version_id, chunk_id, created_by, stance
        ) values (
            'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
            '33333333-3333-4333-8333-333333333333',
            '44444444-4444-4444-8444-444444444444',
            '55555555-5555-4555-8555-555555555555',
            '22222222-2222-4222-8222-222222222222',
            'supports'
        )
    $$,
    'P0001',
    'claim evidence source provenance is inconsistent',
    'user B cannot attach project A evidence to a project B claim'
);

select throws_ok(
    $$
        insert into public.writing_research_links (
            project_id, document_id, created_by, kind, entity_id
        ) values (
            'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            '12121212-1212-4212-8212-121212121212',
            '22222222-2222-4222-8222-222222222222',
            'claim',
            'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
        )
    $$,
    'P0001',
    'linked claim must belong to the same project',
    'user B cannot attach project A research to a project B manuscript'
);

set local request.jwt.claim.sub = '11111111-1111-4111-8111-111111111111';

select results_eq(
    $$
        select status
        from public.sources
        where id = '66666666-6666-4666-8666-666666666666'
    $$,
    array['processing'],
    'denied cross-project recovery leaves project A stale source untouched'
);

select results_eq(
    $$
        select status
        from public.source_versions
        where id = '77777777-7777-4777-8777-777777777777'
    $$,
    array['processing'],
    'denied cross-project recovery leaves project A stale version untouched'
);

select results_eq(
    $$
        select coalesce(error_message, '')
        from public.sources
        where id = '33333333-3333-4333-8333-333333333333'
    $$,
    array[''],
    'denied cross-project source update left project A source unchanged'
);

select results_eq(
    $$
        select name
        from storage.objects
        where bucket_id = 'mi-llama-sources'
          and name = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/33333333-3333-4333-8333-333333333333/44444444-4444-4444-8444-444444444444/a-ready.txt'
    $$,
    array[
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/33333333-3333-4333-8333-333333333333/44444444-4444-4444-8444-444444444444/a-ready.txt'
    ]::text[],
    'project A owner can read the project A storage object'
);

select results_eq(
    $$select id from public.sources where id = '33333333-3333-4333-8333-333333333333'$$,
    array['33333333-3333-4333-8333-333333333333'::uuid],
    'project A owner can read the project A source'
);

select results_eq(
    $$select id from public.source_chunks where id = '55555555-5555-4555-8555-555555555555'$$,
    array['55555555-5555-4555-8555-555555555555'::uuid],
    'project A owner can read the project A source chunk'
);

select results_eq(
    $$select id from public.manuscript_documents where id = 'ffffffff-ffff-4fff-8fff-ffffffffffff'$$,
    array['ffffffff-ffff-4fff-8fff-ffffffffffff'::uuid],
    'project A owner can read the project A manuscript'
);

select * from finish();
rollback;
