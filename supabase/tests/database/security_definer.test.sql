begin;

create extension if not exists pgtap with schema extensions;

select extensions.plan(19);

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

create table attacker.projects (id uuid primary key, owner_id uuid not null);
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

select extensions.diag(
    coalesce(
        string_agg(
            format(
                '%s(%s) | config=%s | PUBLIC=%s | anon=%s | authenticated=%s',
                p.proname,
                pg_get_function_identity_arguments(p.oid),
                coalesce(array_to_string(p.proconfig, ','), '<unset>'),
                exists (
                    select 1
                    from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
                    where acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
                ),
                has_function_privilege('anon', p.oid, 'EXECUTE'),
                has_function_privilege('authenticated', p.oid, 'EXECUTE')
            ),
            E'\n'
            order by p.proname, pg_get_function_identity_arguments(p.oid)
        ),
        '<no public SECURITY DEFINER functions>'
    )
)
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.prosecdef;

select extensions.diag(
    coalesce(
        string_agg(
            format('%s inherits %s (admin=%s)', member.rolname, granted.rolname, m.admin_option),
            E'\n' order by member.rolname, granted.rolname
        ),
        '<no anon/authenticated role memberships>'
    )
)
from pg_auth_members m
join pg_roles member on member.oid = m.member
join pg_roles granted on granted.oid = m.roleid
where member.rolname in ('anon', 'authenticated')
   or granted.rolname in ('anon', 'authenticated');

select extensions.diag(
    coalesce(
        string_agg(
            format(
                '%s(%s) ACL grantee=%s privilege=%s',
                p.proname,
                pg_get_function_identity_arguments(p.oid),
                coalesce(grantee.rolname, 'PUBLIC'),
                acl.privilege_type
            ),
            E'\n' order by p.proname, coalesce(grantee.rolname, 'PUBLIC')
        ),
        '<no explicit SECURITY DEFINER ACL entries>'
    )
)
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
left join pg_roles grantee on grantee.oid = acl.grantee
where n.nspname = 'public'
  and p.prosecdef
  and acl.privilege_type = 'EXECUTE';

select extensions.is(
    (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.prosecdef),
    23::bigint,
    'public SECURITY DEFINER surface inventory is stable'
);

select extensions.ok(
    not exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.prosecdef
          and coalesce(array_to_string(p.proconfig, ','), '') not in (
              'search_path=public',
              'search_path=public, storage'
          )
    ),
    'every public SECURITY DEFINER pins a trusted search_path'
);

select extensions.ok(
    not exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
        where n.nspname = 'public' and p.prosecdef
          and acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
    ),
    'no public SECURITY DEFINER is executable by PUBLIC'
);

select extensions.ok(
    not exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.prosecdef
          and has_function_privilege('anon', p.oid, 'EXECUTE')
    ),
    'anon cannot execute any public SECURITY DEFINER'
);

select extensions.is(
    (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.prosecdef and has_function_privilege('authenticated', p.oid, 'EXECUTE')),
    20::bigint,
    'current authenticated SECURITY DEFINER execution surface is inventoried'
);

set local role anon;
select extensions.throws_ok(
    $$select public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')$$,
    '42501', null,
    'anonymous direct RPC-style invocation is denied'
);
reset role;

set local role authenticated;
set local request.jwt.claim.sub = '22222222-2222-4222-8222-222222222222';

select extensions.ok(not public.is_project_owner('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'outsider cannot forge ownership through direct helper invocation');
select extensions.ok(not public.is_project_member('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', array['editor','researcher','owner','service_role','anything']), 'caller-controlled allowed_roles cannot fabricate membership');
select extensions.ok(not public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'outsider cannot use can_access_project as an RLS bypass');
select extensions.ok(not public.can_edit_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'outsider cannot use can_edit_project as a mutation bypass');
select extensions.ok(public.is_project_owner('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'), 'legitimate owner is recognized');
select extensions.ok(public.can_access_project('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'), 'legitimate owner retains access authorization');
select extensions.ok(public.can_edit_project('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'), 'legitimate owner retains edit authorization');

set local request.jwt.claim.role = 'service_role';
select extensions.ok(not public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'forging a JWT role claim does not grant another project access');

set local search_path = attacker, public;
select extensions.ok(not public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'caller search_path poisoning cannot redirect SECURITY DEFINER internals');

set local request.jwt.claim.sub = '33333333-3333-4333-8333-333333333333';
set local request.jwt.claim.role = 'authenticated';
select extensions.ok(public.is_project_member('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', null), 'reader membership is recognized');
select extensions.ok(public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'reader can access the project');
select extensions.ok(not public.can_edit_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'reader cannot escalate to edit authorization');
select extensions.ok(not public.is_project_owner('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 'reader cannot escalate to ownership');

select * from extensions.finish();
rollback;
