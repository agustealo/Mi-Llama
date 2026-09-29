begin;

-- Supabase installs default function privileges for API roles. Revoking only
-- from PUBLIC is therefore not sufficient for SECURITY DEFINER functions:
-- anon/authenticated may retain explicit EXECUTE grants from those defaults.
-- Normalize the complete current definer surface first, then expose only the
-- reviewed authenticated RPC/authorization boundary.
do $$
declare
    fn regprocedure;
begin
    for fn in
        select p.oid::regprocedure
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.prosecdef
    loop
        execute format('revoke execute on function %s from public', fn);
        execute format('revoke execute on function %s from anon', fn);
        execute format('revoke execute on function %s from authenticated', fn);
    end loop;
end;
$$;

-- Project authorization helpers. These intentionally bypass table RLS only to
-- answer authorization predicates from auth.uid(); they do not trust caller
-- supplied identity or JWT role claims.
grant execute on function public.is_project_owner(uuid) to authenticated;
grant execute on function public.is_project_member(uuid, text[]) to authenticated;
grant execute on function public.can_access_project(uuid) to authenticated;
grant execute on function public.can_edit_project(uuid) to authenticated;

-- Authenticated transactional RPCs. Each function owns its authorization and
-- project-scope checks before performing privileged writes.
grant execute on function public.acquire_conversation_reply_lease(uuid, integer)
    to authenticated;
grant execute on function public.renew_conversation_reply_lease(uuid, uuid, integer)
    to authenticated;
grant execute on function public.release_conversation_reply_lease(uuid, uuid)
    to authenticated;
grant execute on function public.create_manuscript_revision(uuid, uuid, text)
    to authenticated;
grant execute on function public.create_manuscript_revision_result(uuid, uuid, text)
    to authenticated;
grant execute on function public.persist_writing_analysis(
    uuid, uuid, uuid, text, integer, integer, jsonb
) to authenticated;
grant execute on function public.review_writing_finding(uuid, uuid, text)
    to authenticated;
grant execute on function public.promote_writing_finding_to_question(uuid, uuid, integer)
    to authenticated;
grant execute on function public.apply_writing_proposal(
    uuid, uuid, uuid, bigint, jsonb, text
) to authenticated;
grant execute on function public.checkpoint_manuscript_draft(uuid, uuid, bigint)
    to authenticated;
grant execute on function public.promote_writing_evidence(
    uuid, uuid, uuid, bigint, integer, integer, uuid, text, text
) to authenticated;
grant execute on function public.insert_writing_citation(
    uuid, uuid, uuid, uuid, bigint, bigint, text, text, text
) to authenticated;
grant execute on function public.insert_writing_citation_structured(
    uuid, uuid, uuid, uuid, bigint, bigint, text, text, text, jsonb, text
) to authenticated;

-- Intentionally not granted to API roles:
--   cleanup_failed_source_ingests_after_ready()
--   insert_writing_citation_core(...)
--   materialize_claim_evidence_effects()
--   populate_manuscript_revision_editor_state()
--   sync_revision_editor_state_on_base_advance()
--   touch_conversation_activity()
-- They are trigger/internal implementation authorities, not RPC endpoints.

commit;
