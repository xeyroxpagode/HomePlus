-- Phase 6: messages retain only a Planner task reference. Planner remains the source of truth.
alter table public.messaging_messages
  add column if not exists context_entity_id uuid null;

alter table public.messaging_messages
  drop constraint if exists messaging_messages_text_body_check;

alter table public.messaging_messages
  add constraint messaging_messages_payload_check check (
    (message_type = 'text' and length(btrim(body)) between 1 and 4000 and context_entity_id is null)
    or (message_type = 'task' and body = '' and context_entity_id is not null)
  );

create index if not exists messaging_messages_task_context_idx
  on public.messaging_messages (context_entity_id) where message_type = 'task';

create or replace function public.messaging_send_task_message(
  p_conversation_id uuid,
  p_task_id uuid,
  p_client_message_id uuid
)
returns public.messaging_messages
language plpgsql
security definer
set search_path = public
as $$
declare
  v_conversation public.messaging_conversations%rowtype;
  v_sender_membership_id uuid;
  v_existing public.messaging_messages%rowtype;
  v_message public.messaging_messages%rowtype;
  v_sequence bigint;
begin
  select * into v_conversation from public.messaging_conversations
  where id = p_conversation_id and archived_at is null for update;
  if not found or not public.is_active_household_member(v_conversation.household_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;
  v_sender_membership_id := public.messaging_current_membership_id(v_conversation.household_id);
  if v_sender_membership_id is null or not public.messaging_can_access_conversation(p_conversation_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;
  if not exists (select 1 from public.planner_tasks t where t.id = p_task_id and t.household_id = v_conversation.household_id and t.trashed_at is null) then
    raise exception 'messaging_task_not_available' using errcode = 'P0002';
  end if;
  select * into v_existing from public.messaging_messages where conversation_id = p_conversation_id and sender_membership_id = v_sender_membership_id and client_message_id = p_client_message_id;
  if found then return v_existing; end if;
  v_sequence := v_conversation.next_message_sequence;
  update public.messaging_conversations set next_message_sequence = v_sequence + 1, last_message_at = now(), last_message_preview = 'Tarea compartida', last_message_sender_membership_id = v_sender_membership_id where id = p_conversation_id;
  insert into public.messaging_messages (conversation_id, sender_membership_id, sequence, message_type, body, context_entity_id, client_message_id)
  values (p_conversation_id, v_sender_membership_id, v_sequence, 'task', '', p_task_id, p_client_message_id)
  returning * into v_message;
  return v_message;
end;
$$;

revoke all on function public.messaging_send_task_message(uuid, uuid, uuid) from public, anon;
grant execute on function public.messaging_send_task_message(uuid, uuid, uuid) to authenticated;
