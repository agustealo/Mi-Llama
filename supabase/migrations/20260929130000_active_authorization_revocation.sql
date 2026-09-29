begin;

create or replace function public.renew_conversation_reply_lease(
    p_conversation_id uuid,
    p_lease_token uuid,
    p_ttl_seconds integer
)
returns table(renewed boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid;
    target_project_id uuid;
    updated_count integer;
begin
    caller := auth.uid();
    if caller is null then
        raise exception 'authentication required';
    end if;
    if p_ttl_seconds < 30 or p_ttl_seconds > 1800 then
        raise exception 'conversation reply lease TTL must be between 30 and 1800 seconds';
    end if;

    select lease.project_id
    into target_project_id
    from public.conversation_reply_leases lease
    where lease.conversation_id = p_conversation_id
      and lease.lease_token = p_lease_token
      and lease.acquired_by = caller
      and lease.expires_at > now();

    if not found then
        raise exception 'conversation reply lease is no longer held';
    end if;
    if not public.can_edit_project(target_project_id) then
        raise exception 'project edit access required';
    end if;

    update public.conversation_reply_leases lease
    set expires_at = now() + make_interval(secs => p_ttl_seconds)
    where lease.conversation_id = p_conversation_id
      and lease.lease_token = p_lease_token
      and lease.acquired_by = caller
      and lease.expires_at > now();

    get diagnostics updated_count = row_count;
    if updated_count <> 1 then
        raise exception 'conversation reply lease is no longer held';
    end if;

    return query select true;
end;
$$;

revoke all on function public.renew_conversation_reply_lease(uuid, uuid, integer)
    from public, anon;
grant execute on function public.renew_conversation_reply_lease(uuid, uuid, integer)
    to authenticated;

commit;
