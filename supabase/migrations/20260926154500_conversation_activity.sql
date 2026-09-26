begin;

create view public.conversation_activity
with (security_invoker = true)
as
select
    conversation.id,
    conversation.project_id,
    conversation.document_id,
    conversation.created_by,
    conversation.title,
    conversation.model,
    conversation.created_at,
    conversation.updated_at,
    greatest(
        conversation.updated_at,
        coalesce(max(message.created_at), conversation.updated_at)
    ) as activity_at
from public.conversations as conversation
left join public.messages as message
    on message.conversation_id = conversation.id
group by conversation.id;

grant select on public.conversation_activity to authenticated;

commit;
