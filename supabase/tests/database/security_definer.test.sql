begin;

create extension if not exists pgtap with schema extensions;

select plan(19);

insert into auth.users (id, email, raw_user_meta_data)
values
    ('11111111-1111-4111-8111-111111111111', 'definer-owner-a@example.test', '{}'::jsonb),
    ('22222222-2222-4222-8222-222222222222', 'definer-owner-b@example.test', '{}'::jsonb),
    ('33333333-3333-4333-8333-333333333333', 'definer-reader@example.test', '{}'::jsonb)
on conflict (id) do nothing;

insert into public.projects (id, owner_id, title)
values
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '11111111-1111-4111-8111-111111111111', 'Definer Project A'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '22222222-2222-4222-8222-222222222222', 'Definer Project B');

insert into public.project_members (project_id, user_id, role)
values (
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '33333333-3333-4333-8333-333333333333',
    'reader'
);

create schema attacker;
grant usage on schema attacker to authenticated;

create table attacker.projects (
    id uuid primary key,
    owner_id uuid not null
);
insert into attacker.projects (id, owner_id)
values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '22222222-2222-4222-8222-222222222222');

create function attacker.is_project_owner(uuid)
returns boolean
language sql
as $$ select true $$;

create function attacker.is_project_member(uuid, text[])
returns boolean
language sql
as $$ select true $$;

grant execute on function attacker.is_project_owner(uuid) to authenticated;
grant execute on function attacker.is_project_member(uuid, text[]) to authenticated;

select is(
    (
        select count(*)
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.prosecdef
    ),
    4::bigint,
    'public SECURITY DEFINER surface is explicitly reviewed'
);

select ok(
    not exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.prosecdef
          and not ('search_path=public' = any(coalesce(p.proconfig, array[]::text[])))
    ),
    'every public SECURITY DEFINER pins search_path to public'
);

select ok(
    not exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
        where n.nspname = 'public'
          and p.prosecdef
          and acl.grantee = 0
          and acl.privilege_type = 'EXECUTE'
    ),
    'no public SECURITY DEFINER is executable by PUBLIC'
);

select ok(
    not exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.prosecdef
          and has_function_privilege('anon', p.oid, 'EXECUTE')
    ),
    'anon cannot execute any public SECURITY DEFINER'
);

select is(
    (
        select count(*)
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.prosecdef
          and has_function_privilege('authenticated', p.oid, 'EXECUTE')
    ),
    4::bigint,
    'authenticated can execute only the reviewed public SECURITY DEFINER helpers'
);

set local role anon;
select throws_ok(
    $$select public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')$$,
    '42501',
    null,
    'anonymous direct RPC-style invocation is denied'
);
reset role;

set local role authenticated;
set local request.jwt.claim.sub = '22222222-2222-4222-8222-222222222222';

select is(
    public.is_project_owner('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    false,
    'outsider cannot forge ownership of another project through direct helper invocation'
);

select is(
    public.is_project_member(
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        array['editor', 'researcher', 'owner', 'service_role', 'anything']
    ),
    false,
    'caller-controlled allowed_roles cannot fabricate membership'
);

select is(
    public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    false,
    'outsider cannot use can_access_project as an RLS bypass'
);

select is(
    public.can_edit_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    false,
    'outsider cannot use can_edit_project as a mutation bypass'
);

select is(
    public.is_project_owner('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
    true,
    'legitimate owner is recognized by direct helper invocation'
);

select is(
    public.can_access_project('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
    true,
    'legitimate owner retains direct access authorization'
);

select is(
    public.can_edit_project('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
    true,
    'legitimate owner retains direct edit authorization'
);

set local request.jwt.claim.role = 'service_role';
select is(
    public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    false,
    'forging a JWT role claim does not grant another project access'
);

set local search_path = attacker, public;
select is(
    public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    false,
    'caller search_path poisoning cannot redirect SECURITY DEFINER internals'
);

set local request.jwt.claim.sub = '33333333-3333-4333-8333-333333333333';
set local request.jwt.claim.role = 'authenticated';

select is(
    public.is_project_member('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', null),
    true,
    'reader membership is recognized'
);

select is(
    public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    true,
    'reader can access the project'
);

select is(
    public.can_edit_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    false,
    'reader membership cannot escalate to edit authorization'
);

select is(
    public.is_project_owner('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    false,
    'reader membership cannot escalate to ownership'
);

select * from finish();
rollback;
