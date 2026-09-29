begin;

create extension if not exists pgtap with schema extensions;

select extensions.plan(8);

insert into auth.users (id, email, raw_user_meta_data)
values
    ('91111111-1111-4111-8111-111111111111', 'cleanup-owner@example.test', '{}'::jsonb),
    ('92222222-2222-4222-8222-222222222222', 'cleanup-editor@example.test', '{}'::jsonb)
on conflict (id) do nothing;

insert into public.projects (id, owner_id, title)
values (
    '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '91111111-1111-4111-8111-111111111111',
    'Cleanup Revocation Project'
);

insert into public.project_members (project_id, user_id, role)
values (
    '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '92222222-2222-4222-8222-222222222222',
    'editor'
);

insert into public.sources (
    id, project_id, created_by, filename, media_type, kind,
    checksum_sha256, size_bytes, status
)
values
    (
        '93333333-3333-4333-8333-333333333333',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '92222222-2222-4222-8222-222222222222',
        'owned-processing.txt', 'text/plain', 'text', repeat('d', 64), 128, 'processing'
    ),
    (
        '94444444-4444-4444-8444-444444444444',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '91111111-1111-4111-8111-111111111111',
        'owner-processing.txt', 'text/plain', 'text', repeat('e', 64), 128, 'processing'
    ),
    (
        '95555555-5555-4555-8555-555555555555',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '92222222-2222-4222-8222-222222222222',
        'owned-ready.txt', 'text/plain', 'text', repeat('f', 64), 128, 'ready'
    );

insert into public.source_versions (
    id, source_id, project_id, created_by, version_number, storage_path,
    checksum_sha256, parser, character_count, status, research_status
)
values
    (
        '96666666-6666-4666-8666-666666666666',
        '93333333-3333-4333-8333-333333333333',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '92222222-2222-4222-8222-222222222222',
        1,
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/93333333-3333-4333-8333-333333333333/96666666-6666-4666-8666-666666666666/owned-processing.txt',
        repeat('d', 64), 'plain-text', 128, 'processing', 'not_indexed'
    ),
    (
        '97777777-7777-4777-8777-777777777777',
        '94444444-4444-4444-8444-444444444444',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '91111111-1111-4111-8111-111111111111',
        1,
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/94444444-4444-4444-8444-444444444444/97777777-7777-4777-8777-777777777777/owner-processing.txt',
        repeat('e', 64), 'plain-text', 128, 'processing', 'not_indexed'
    ),
    (
        '98888888-8888-4888-8888-888888888888',
        '95555555-5555-4555-8555-555555555555',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '92222222-2222-4222-8222-222222222222',
        1,
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/95555555-5555-4555-8555-555555555555/98888888-8888-4888-8888-888888888888/owned-ready.txt',
        repeat('f', 64), 'plain-text', 128, 'ready', 'disabled'
    );

insert into storage.objects (bucket_id, name)
values
    (
        'mi-llama-sources',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/93333333-3333-4333-8333-333333333333/96666666-6666-4666-8666-666666666666/owned-processing.txt'
    ),
    (
        'mi-llama-sources',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/94444444-4444-4444-8444-444444444444/97777777-7777-4777-8777-777777777777/owner-processing.txt'
    ),
    (
        'mi-llama-sources',
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/95555555-5555-4555-8555-555555555555/98888888-8888-4888-8888-888888888888/owned-ready.txt'
    );

set local role authenticated;
set local request.jwt.claim.sub = '92222222-2222-4222-8222-222222222222';
set local request.jwt.claim.role = 'authenticated';

select extensions.ok(
    public.can_edit_project('9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'source creator has edit authority when ingest begins'
);

reset role;
delete from public.project_members
where project_id = '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  and user_id = '92222222-2222-4222-8222-222222222222';

set local role authenticated;
set local request.jwt.claim.sub = '92222222-2222-4222-8222-222222222222';
set local request.jwt.claim.role = 'authenticated';

select extensions.ok(
    not public.can_access_project('9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'membership removal revokes project access immediately'
);

select extensions.is_empty(
    $$
        update public.sources
        set error_message = 'must not persist after revocation'
        where id = '93333333-3333-4333-8333-333333333333'
        returning id
    $$,
    'revoked source creator cannot continue mutating source state'
);

select extensions.ok(
    public.can_cleanup_source_storage_object(
        '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/93333333-3333-4333-8333-333333333333/96666666-6666-4666-8666-666666666666/owned-processing.txt'
    ),
    'revoked creator retains narrow cleanup authority for its processing object'
);

select extensions.results_eq(
    $$
        delete from storage.objects
        where bucket_id = 'mi-llama-sources'
          and name = '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/93333333-3333-4333-8333-333333333333/96666666-6666-4666-8666-666666666666/owned-processing.txt'
        returning 1::bigint
    $$,
    array[1::bigint],
    'revoked creator can delete only its own processing ingest object'
);

select extensions.is_empty(
    $$
        delete from storage.objects
        where bucket_id = 'mi-llama-sources'
          and name = '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/94444444-4444-4444-8444-444444444444/97777777-7777-4777-8777-777777777777/owner-processing.txt'
        returning 1::bigint
    $$,
    'revoked creator cannot delete another user''s processing object'
);

select extensions.is_empty(
    $$
        delete from storage.objects
        where bucket_id = 'mi-llama-sources'
          and name = '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/95555555-5555-4555-8555-555555555555/98888888-8888-4888-8888-888888888888/owned-ready.txt'
        returning 1::bigint
    $$,
    'revoked creator cannot delete its own ready source artifact'
);

reset role;

select extensions.is(
    (
        select count(*)
        from storage.objects
        where bucket_id = 'mi-llama-sources'
          and name like '9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/%'
    ),
    2::bigint,
    'cleanup removes only the failed in-flight blob and preserves protected objects'
);

select * from extensions.finish();
rollback;
