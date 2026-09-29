begin;

create extension if not exists pgtap with schema extensions;

select extensions.plan(22);

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

insert into public.conversations (id, project_id, created_by, title, model)
values (
    '44444444-4444-4444-8444-444444444444',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '11111111-1111-4111-8111-111111111111',
    'Project A conversation',
    'test-model'
);

create temporary table reviewed_security_definers (
    signature regprocedure primary key,
    api_exposed boolean not null
) on commit drop;

insert into reviewed_security_definers (signature, api_exposed)
values
    ('public.acquire_conversation_reply_lease(uuid,integer)'::regprocedure, true),
    ('public.apply_writing_proposal(uuid,uuid,uuid,bigint,jsonb,text)'::regprocedure, true),
    ('public.can_access_project(uuid)'::regprocedure, true),
    ('public.can_edit_project(uuid)'::regprocedure, true),
    ('public.checkpoint_manuscript_draft(uuid,uuid,bigint)'::regprocedure, true),
    ('public.cleanup_failed_source_ingests_after_ready()'::regprocedure, false),
    ('public.create_manuscript_revision(uuid,uuid,text)'::regprocedure, true),
    ('public.create_manuscript_revision_result(uuid,uuid,text)'::regprocedure, true),
    ('public.insert_writing_citation(uuid,uuid,uuid,uuid,bigint,bigint,text,text,text)'::regprocedure, true),
    ('public.insert_writing_citation_core(uuid,uuid,uuid,uuid,bigint,bigint,text,text,text,jsonb,text)'::regprocedure, false),
    ('public.insert_writing_citation_structured(uuid,uuid,uuid,uuid,bigint,bigint,text,text,text,jsonb,text)'::regprocedure, true),
    ('public.is_project_member(uuid,text[])'::regprocedure, true),
    ('public.is_project_owner(uuid)'::regprocedure, true),
    ('public.materialize_claim_evidence_effects()'::regprocedure, false),
    ('public.persist_writing_analysis(uuid,uuid,uuid,text,integer,integer,jsonb)'::regprocedure, true),
    ('public.populate_manuscript_revision_editor_state()'::regprocedure, false),
    ('public.promote_writing_evidence(uuid,uuid,uuid,bigint,integer,integer,uuid,text,text)'::regprocedure, true),
    ('public.promote_writing_finding_to_question(uuid,uuid,integer)'::regprocedure, true),
    ('public.release_conversation_reply_lease(uuid,uuid)'::regprocedure, true),
    ('public.renew_conversation_reply_lease(uuid,uuid,integer)'::regprocedure, true),
    ('public.review_writing_finding(uuid,uuid,text)'::regprocedure, true),
    ('public.sync_revision_editor_state_on_base_advance()'::regprocedure, false),
    ('public.touch_conversation_activity()'::regprocedure, false);

create schema attacker;
grant usage on schema attacker to authenticated;
create table attacker.projects (id uuid primary key, owner_id uuid not null);
insert into attacker.projects (id, owner_id)
values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '22222222-2222-4222-8222-222222222222');
create function attacker.is_project_owner(uuid) returns boolean language sql as $$ select true $$;
create function attacker.is_project_member(uuid, text[]) returns boolean language sql as $$ select true $$;
grant execute on function attacker.is_project_owner(uuid) to authenticated;
grant execute on function attacker.is_project_member(uuid, text[]) to authenticated;

select extensions.ok(
    not exists (
        select p.oid
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.prosecdef
        except
        select signature::oid from reviewed_security_definers
    )
    and not exists (
        select signature::oid from reviewed_security_definers
        except
        select p.oid
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.prosecdef
    ),
    'public SECURITY DEFINER surface exactly matches the reviewed registry'
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
        where n.nspname = 'public'
          and p.prosecdef
          and acl.grantee = 0
          and acl.privilege_type = 'EXECUTE'
    ),
    'PUBLIC cannot execute any public SECURITY DEFINER'
);

select extensions.ok(
    not exists (
        select 1
        from reviewed_security_definers reviewed
        where has_function_privilege('anon', reviewed.signature::oid, 'EXECUTE')
    ),
    'anon cannot execute any reviewed SECURITY DEFINER'
);

select extensions.ok(
    not exists (
        select 1
        from reviewed_security_definers reviewed
        where reviewed.api_exposed
          and not has_function_privilege('authenticated', reviewed.signature::oid, 'EXECUTE')
    ),
    'authenticated can execute every reviewed API SECURITY DEFINER'
);

select extensions.ok(
    not exists (
        select 1
        from reviewed_security_definers reviewed
        where not reviewed.api_exposed
          and has_function_privilege('authenticated', reviewed.signature::oid, 'EXECUTE')
    ),
    'authenticated cannot execute internal trigger/core SECURITY DEFINER functions'
);

set local role anon;
select extensions.throws_ok(
    $$select public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')$$,
    '42501',
    null,
    'anonymous direct authorization-helper invocation is denied at EXECUTE privilege'
);
reset role;

set local role authenticated;
select extensions.throws_ok(
    $$select public.touch_conversation_activity()$$,
    '42501',
    null,
    'authenticated callers cannot invoke an internal trigger authority directly'
);

set local request.jwt.claim.sub = '22222222-2222-4222-8222-222222222222';
set local request.jwt.claim.role = 'authenticated';

select extensions.ok(
    not public.is_project_owner('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'outsider cannot forge ownership through direct helper invocation'
);
select extensions.ok(
    not public.is_project_member(
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        array['editor','researcher','owner','service_role','anything']
    ),
    'caller-controlled allowed_roles cannot fabricate membership'
);
select extensions.ok(
    not public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'outsider cannot use can_access_project as an RLS bypass'
);
select extensions.ok(
    not public.can_edit_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'outsider cannot use can_edit_project as a mutation bypass'
);
select extensions.ok(
    public.is_project_owner('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
    'legitimate owner is recognized'
);
select extensions.ok(
    public.can_access_project('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
    'legitimate owner retains access authorization'
);
select extensions.ok(
    public.can_edit_project('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
    'legitimate owner retains edit authorization'
);

set local request.jwt.claim.role = 'service_role';
select extensions.ok(
    not public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'forging a JWT role claim does not grant another project access'
);

set local search_path = attacker, public, extensions;
select extensions.ok(
    not public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'caller search_path poisoning cannot redirect SECURITY DEFINER internals'
);

select extensions.throws_ok(
    $$select * from public.acquire_conversation_reply_lease('44444444-4444-4444-8444-444444444444', 60)$$,
    'P0001',
    'project edit access required',
    'mutating SECURITY DEFINER RPC rejects a forged cross-project target'
);

set local request.jwt.claim.sub = '33333333-3333-4333-8333-333333333333';
set local request.jwt.claim.role = 'authenticated';
select extensions.ok(
    public.is_project_member('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', null),
    'reader membership is recognized'
);
select extensions.ok(
    public.can_access_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'reader can access the project'
);
select extensions.ok(
    not public.can_edit_project('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'reader cannot escalate to edit authorization'
);
select extensions.ok(
    not public.is_project_owner('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    'reader cannot escalate to ownership'
);

select * from extensions.finish();
rollback;
