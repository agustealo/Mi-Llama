begin;

create extension if not exists pgtap with schema extensions;

select extensions.plan(15);

insert into auth.users (id, email, raw_user_meta_data)
values
    ('71111111-1111-4111-8111-111111111111', 'rpc-owner-a@example.test', '{}'::jsonb),
    ('72222222-2222-4222-8222-222222222222', 'rpc-owner-b@example.test', '{}'::jsonb)
on conflict (id) do nothing;

insert into public.projects (id, owner_id, title)
values
    ('7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '71111111-1111-4111-8111-111111111111', 'RPC Project A'),
    ('7bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '72222222-2222-4222-8222-222222222222', 'RPC Project B');

insert into public.conversations (id, project_id, created_by, title, model)
values (
    '74444444-4444-4444-8444-444444444444',
    '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '71111111-1111-4111-8111-111111111111',
    'RPC Project A conversation',
    'test-model'
);

set local role authenticated;
set local request.jwt.claim.sub = '72222222-2222-4222-8222-222222222222';
set local request.jwt.claim.role = 'authenticated';

select extensions.throws_ok(
    $$select * from public.acquire_conversation_reply_lease('74444444-4444-4444-8444-444444444444', 60)$$,
    'P0001', 'project edit access required',
    'acquire conversation lease rejects another project'
);

select extensions.throws_ok(
    $$select * from public.apply_writing_proposal(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555',
        '76666666-6666-4666-8666-666666666666',
        1, '{}'::jsonb, 'forged'
    )$$,
    'P0001', 'project edit access required',
    'apply writing proposal rejects another project'
);

select extensions.throws_ok(
    $$select * from public.checkpoint_manuscript_draft(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555', 1
    )$$,
    'P0001', 'project edit access required',
    'checkpoint manuscript draft rejects another project'
);

select extensions.throws_ok(
    $$select * from public.create_manuscript_revision(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555', 'forged revision'
    )$$,
    'P0001', 'project edit access required',
    'create manuscript revision rejects another project'
);

select extensions.throws_ok(
    $$select * from public.create_manuscript_revision_result(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555', 'forged revision'
    )$$,
    'P0001', 'project edit access required',
    'create manuscript revision result rejects another project'
);

select extensions.throws_ok(
    $$select * from public.insert_writing_citation(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555',
        '76666666-6666-4666-8666-666666666666',
        '77777777-7777-4777-8777-777777777777',
        1, 1, 'apa', '(forged)', 'forged bibliography'
    )$$,
    'P0001', 'project edit access required',
    'insert writing citation rejects another project'
);

select extensions.throws_ok(
    $$select * from public.insert_writing_citation_structured(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555',
        '76666666-6666-4666-8666-666666666666',
        '77777777-7777-4777-8777-777777777777',
        1, 1, 'apa', '(forged)', 'forged bibliography', '{}'::jsonb, 'forged'
    )$$,
    'P0001', 'project edit access required',
    'structured citation insertion rejects another project'
);

select extensions.throws_ok(
    $$select * from public.persist_writing_analysis(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555',
        '76666666-6666-4666-8666-666666666666',
        'test-model', 0, 1, '[]'::jsonb
    )$$,
    'P0001', 'project edit access required',
    'persist writing analysis rejects another project'
);

select extensions.throws_ok(
    $$select * from public.promote_writing_evidence(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '75555555-5555-4555-8555-555555555555',
        '76666666-6666-4666-8666-666666666666',
        1, 0, 1,
        '77777777-7777-4777-8777-777777777777',
        'supports', 'forged'
    )$$,
    'P0001', 'project edit access required',
    'promote writing evidence rejects another project'
);

select extensions.throws_ok(
    $$select * from public.promote_writing_finding_to_question(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '76666666-6666-4666-8666-666666666666', 3
    )$$,
    'P0001', 'project edit access required',
    'promote writing finding rejects another project'
);

select extensions.throws_ok(
    $$select * from public.review_writing_finding(
        '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        '76666666-6666-4666-8666-666666666666', 'confirmed'
    )$$,
    'P0001', 'project edit access required',
    'review writing finding rejects another project'
);

select extensions.throws_ok(
    $$select * from public.renew_conversation_reply_lease(
        '74444444-4444-4444-8444-444444444444',
        '78888888-8888-4888-8888-888888888888', 60
    )$$,
    'P0001', 'conversation reply lease is no longer held',
    'lease renewal rejects another caller without the held token'
);

select extensions.is(
    (
        select released
        from public.release_conversation_reply_lease(
            '74444444-4444-4444-8444-444444444444',
            '78888888-8888-4888-8888-888888888888'
        )
    ),
    false,
    'lease release cannot delete another caller lease'
);

reset role;

select extensions.is(
    (select count(*) from public.conversation_reply_leases),
    0::bigint,
    'failed cross-project lease attacks create no durable lease state'
);

select extensions.is(
    (select count(*) from public.learning_signals where project_id = '7aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    0::bigint,
    'failed cross-project writing RPC attacks create no learning signals'
);

select * from extensions.finish();
rollback;
