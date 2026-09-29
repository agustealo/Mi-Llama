begin;

create extension if not exists pgtap with schema extensions;

select extensions.plan(8);

insert into auth.users (id, email, raw_user_meta_data)
values
    ('81111111-1111-4111-8111-111111111111', 'revocation-owner@example.test', '{}'::jsonb),
    ('82222222-2222-4222-8222-222222222222', 'revocation-editor@example.test', '{}'::jsonb)
on conflict (id) do nothing;

insert into public.projects (id, owner_id, title)
values (
    '8aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '81111111-1111-4111-8111-111111111111',
    'Revocation Project'
);

insert into public.project_members (project_id, user_id, role)
values (
    '8aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '82222222-2222-4222-8222-222222222222',
    'editor'
);

insert into public.conversations (id, project_id, created_by, title, model)
values (
    '84444444-4444-4444-8444-444444444444',
    '8aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '81111111-1111-4111-8111-111111111111',
    'Revocation conversation',
    'test-model'
);

create temporary table revocation_probe (
    lease_token uuid not null
) on commit drop;
grant select, insert on revocation_probe to authenticated;

set local role authenticated;
set local request.jwt.claim.sub = '82222222-2222-4222-8222-222222222222';
set local request.jwt.claim.role = 'authenticated';

select extensions.ok(
    public.can_edit_project('8aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'editor has edit authority when work begins'
);

insert into revocation_probe (lease_token)
select lease_token
from public.acquire_conversation_reply_lease(
    '84444444-4444-4444-8444-444444444444',
    600
);

select extensions.is(
    (select count(*) from revocation_probe),
    1::bigint,
    'editor can acquire the active reply lease before revocation'
);

reset role;
update public.project_members
set role = 'reader'
where project_id = '8aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  and user_id = '82222222-2222-4222-8222-222222222222';

set local role authenticated;
set local request.jwt.claim.sub = '82222222-2222-4222-8222-222222222222';
set local request.jwt.claim.role = 'authenticated';

select extensions.ok(
    not public.can_edit_project('8aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'reader downgrade takes effect immediately for edit authority'
);

select extensions.throws_ok(
    format(
        'select * from public.renew_conversation_reply_lease(%L::uuid, %L::uuid, 600)',
        '84444444-4444-4444-8444-444444444444',
        (select lease_token::text from revocation_probe)
    ),
    'P0001',
    'project edit access required',
    'active reply lease cannot be renewed after edit authority is revoked'
);

select extensions.throws_ok(
    $$insert into public.messages (conversation_id, created_by, role, content)
      values (
          '84444444-4444-4444-8444-444444444444',
          '82222222-2222-4222-8222-222222222222',
          'assistant',
          'must not commit after revocation'
      )$$,
    '42501',
    null,
    'final assistant publication is rejected after edit authority is revoked'
);

select extensions.is(
    (
        select released
        from public.release_conversation_reply_lease(
            '84444444-4444-4444-8444-444444444444',
            (select lease_token from revocation_probe)
        )
    ),
    true,
    'revoked caller can still release its own lease for cleanup'
);

reset role;

select extensions.is(
    (
        select count(*)
        from public.messages
        where conversation_id = '84444444-4444-4444-8444-444444444444'
    ),
    0::bigint,
    'revoked in-flight turn leaves no assistant message behind'
);

select extensions.is(
    (
        select count(*)
        from public.conversation_reply_leases
        where conversation_id = '84444444-4444-4444-8444-444444444444'
    ),
    0::bigint,
    'revoked in-flight turn leaves no durable lease behind'
);

select * from extensions.finish();
rollback;
