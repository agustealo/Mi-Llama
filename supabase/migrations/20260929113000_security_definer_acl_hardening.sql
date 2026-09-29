begin;

-- Supabase's bootstrap default privileges grant EXECUTE on newly-created
-- functions to anon/authenticated unless a migration explicitly removes them.
-- For SECURITY DEFINER functions that is too permissive as a default: anonymous
-- execution must never be inherited accidentally, and authenticated RPC access
-- should be explicit at the defining migration.
alter default privileges in schema public
    revoke execute on functions from anon;
alter default privileges in schema public
    revoke execute on functions from authenticated;

-- Normalize every existing public SECURITY DEFINER function. Dynamic revocation
-- keeps this forward migration complete for the full historical function set
-- without rewriting older migrations.
do $$
declare
    fn record;
begin
    for fn in
        select p.oid::regprocedure as identity
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.prosecdef
    loop
        execute format('revoke execute on function %s from anon', fn.identity);
    end loop;
end;
$$;

-- These definers exist only as trigger implementations. They are invoked by
-- PostgreSQL through their bound triggers and are not part of the authenticated
-- RPC surface.
revoke execute on function public.touch_conversation_activity() from authenticated;
revoke execute on function public.materialize_claim_evidence_effects() from authenticated;
revoke execute on function public.cleanup_failed_source_ingests_after_ready() from authenticated;

commit;
