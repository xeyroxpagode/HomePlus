-- HomePlus Messaging V1: household thread + canonical direct messages.
-- Membership, rather than account/person, is the authoritative actor identity.

create table if not exists public.messaging_conversations (
  id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(id) on delete cascade,
  conversation_type text not null check (conversation_type in ('household', 'direct')),
  direct_membership_low_id uuid null references public.household_members(id) on delete cascade,
  direct_membership_high_id uuid null references public.household_members(id) on delete cascade,
  next_message_sequence bigint not null default 1 check (next_message_sequence >= 1),
  last_message_at timestamptz null,
  last_message_preview text null,
  last_message_sender_membership_id uuid null references public.household_members(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz null,
  constraint messaging_conversations_shape_check check (
    (conversation_type = 'household' and direct_membership_low_id is null and direct_membership_high_id is null)
    or
    (conversation_type = 'direct'
      and direct_membership_low_id is not null
      and direct_membership_high_id is not null
      and direct_membership_low_id < direct_membership_high_id)
  )
);

-- A household has one principal active conversation. The predicate makes its
-- creation safe under concurrent first-open requests.
create unique index if not exists messaging_one_active_household_conversation
  on public.messaging_conversations (household_id)
  where conversation_type = 'household' and archived_at is null;

-- A direct is canonical for the same pair of memberships in a household.
create unique index if not exists messaging_one_direct_per_membership_pair
  on public.messaging_conversations (household_id, direct_membership_low_id, direct_membership_high_id)
  where conversation_type = 'direct' and archived_at is null;

create index if not exists messaging_conversations_household_activity_idx
  on public.messaging_conversations (household_id, last_message_at desc nulls last, created_at desc);

create table if not exists public.messaging_conversation_participants (
  conversation_id uuid not null references public.messaging_conversations(id) on delete cascade,
  membership_id uuid not null references public.household_members(id) on delete cascade,
  joined_at timestamptz not null default now(),
  left_at timestamptz null,
  last_read_sequence bigint not null default 0 check (last_read_sequence >= 0),
  last_read_at timestamptz null,
  primary key (conversation_id, membership_id)
);

create index if not exists messaging_participants_membership_idx
  on public.messaging_conversation_participants (membership_id, conversation_id)
  where left_at is null;

create table if not exists public.messaging_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.messaging_conversations(id) on delete cascade,
  sender_membership_id uuid not null references public.household_members(id) on delete restrict,
  sequence bigint not null check (sequence > 0),
  -- V1 accepts text at the API/RPC boundary. This remains an extensible
  -- discriminator so contextual HomePlus messages do not require a table redesign.
  message_type text not null default 'text',
  body text not null,
  client_message_id uuid not null,
  created_at timestamptz not null default now(),
  edited_at timestamptz null,
  deleted_at timestamptz null,
  constraint messaging_messages_text_body_check check (length(btrim(body)) between 1 and 4000),
  unique (conversation_id, sequence),
  unique (conversation_id, sender_membership_id, client_message_id)
);

create index if not exists messaging_messages_conversation_sequence_idx
  on public.messaging_messages (conversation_id, sequence desc);

create or replace function public.messaging_set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists messaging_conversations_set_updated_at on public.messaging_conversations;
create trigger messaging_conversations_set_updated_at
before update on public.messaging_conversations
for each row execute procedure public.messaging_set_updated_at();

-- Security-definer helpers are deliberately tiny and are the single RLS gate
-- for conversation visibility. They always bind the check to auth identity.
create or replace function public.messaging_current_membership_id(p_household_id uuid)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select hm.id
  from public.household_members hm
  where hm.household_id = p_household_id
    and hm.person_id = public.current_person_id()
    and hm.status = 'active'
  limit 1
$$;

create or replace function public.messaging_can_access_conversation(p_conversation_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.messaging_conversations c
    where c.id = p_conversation_id
      and c.archived_at is null
      and public.is_active_household_member(c.household_id)
      and (
        c.conversation_type = 'household'
        or exists (
          select 1
          from public.messaging_conversation_participants cp
          where cp.conversation_id = c.id
            and cp.membership_id = public.messaging_current_membership_id(c.household_id)
            and cp.left_at is null
        )
      )
  )
$$;

create or replace function public.messaging_seed_household_participants(p_conversation_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_household_id uuid;
begin
  select household_id into v_household_id
  from public.messaging_conversations
  where id = p_conversation_id and conversation_type = 'household';

  if v_household_id is null then
    raise exception 'messaging_household_conversation_not_found' using errcode = 'P0002';
  end if;

  insert into public.messaging_conversation_participants (conversation_id, membership_id)
  select p_conversation_id, hm.id
  from public.household_members hm
  where hm.household_id = v_household_id and hm.status = 'active'
  on conflict (conversation_id, membership_id) do update
    set left_at = null;
end;
$$;

create or replace function public.messaging_ensure_household_conversation(p_household_id uuid)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_conversation_id uuid;
begin
  if not public.is_active_household_member(p_household_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;

  insert into public.messaging_conversations (household_id, conversation_type)
  values (p_household_id, 'household')
  on conflict (household_id) where conversation_type = 'household' and archived_at is null do nothing;

  select id into v_conversation_id
  from public.messaging_conversations
  where household_id = p_household_id
    and conversation_type = 'household'
    and archived_at is null;

  perform public.messaging_seed_household_participants(v_conversation_id);
  return v_conversation_id;
end;
$$;

create or replace function public.messaging_ensure_direct_conversation(
  p_household_id uuid,
  p_other_membership_id uuid
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_self_membership_id uuid;
  v_low_id uuid;
  v_high_id uuid;
  v_conversation_id uuid;
begin
  v_self_membership_id := public.messaging_current_membership_id(p_household_id);
  if v_self_membership_id is null then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;

  if p_other_membership_id = v_self_membership_id then
    raise exception 'messaging_direct_requires_another_member' using errcode = '22023';
  end if;

  if not exists (
    select 1 from public.household_members hm
    where hm.id = p_other_membership_id
      and hm.household_id = p_household_id
      and hm.status = 'active'
  ) then
    raise exception 'messaging_invalid_direct_member' using errcode = '42501';
  end if;

  v_low_id := least(v_self_membership_id, p_other_membership_id);
  v_high_id := greatest(v_self_membership_id, p_other_membership_id);

  insert into public.messaging_conversations (
    household_id, conversation_type, direct_membership_low_id, direct_membership_high_id
  ) values (p_household_id, 'direct', v_low_id, v_high_id)
  on conflict (household_id, direct_membership_low_id, direct_membership_high_id)
    where conversation_type = 'direct' and archived_at is null do nothing;

  select id into v_conversation_id
  from public.messaging_conversations
  where household_id = p_household_id
    and conversation_type = 'direct'
    and direct_membership_low_id = v_low_id
    and direct_membership_high_id = v_high_id
    and archived_at is null;

  insert into public.messaging_conversation_participants (conversation_id, membership_id)
  values (v_conversation_id, v_self_membership_id), (v_conversation_id, p_other_membership_id)
  on conflict (conversation_id, membership_id) do update set left_at = null;

  return v_conversation_id;
end;
$$;

create or replace function public.messaging_send_text_message(
  p_conversation_id uuid,
  p_body text,
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
  v_body text;
  v_sequence bigint;
begin
  v_body := btrim(coalesce(p_body, ''));
  if length(v_body) < 1 or length(v_body) > 4000 then
    raise exception 'messaging_invalid_body' using errcode = '22023';
  end if;

  -- Locks the conversation before the idempotency lookup and sequence advance.
  select * into v_conversation
  from public.messaging_conversations
  where id = p_conversation_id and archived_at is null
  for update;

  if not found or not public.is_active_household_member(v_conversation.household_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;

  v_sender_membership_id := public.messaging_current_membership_id(v_conversation.household_id);
  if v_sender_membership_id is null then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;

  if v_conversation.conversation_type = 'direct' and not exists (
    select 1 from public.messaging_conversation_participants cp
    where cp.conversation_id = p_conversation_id
      and cp.membership_id = v_sender_membership_id
      and cp.left_at is null
  ) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;

  if v_conversation.conversation_type = 'household' then
    perform public.messaging_seed_household_participants(p_conversation_id);
  end if;

  select * into v_existing
  from public.messaging_messages
  where conversation_id = p_conversation_id
    and sender_membership_id = v_sender_membership_id
    and client_message_id = p_client_message_id;
  if found then
    return v_existing;
  end if;

  v_sequence := v_conversation.next_message_sequence;
  update public.messaging_conversations
  set next_message_sequence = v_sequence + 1,
      last_message_at = now(),
      last_message_preview = v_body,
      last_message_sender_membership_id = v_sender_membership_id
  where id = p_conversation_id;

  insert into public.messaging_messages (
    conversation_id, sender_membership_id, sequence, message_type, body, client_message_id
  ) values (p_conversation_id, v_sender_membership_id, v_sequence, 'text', v_body, p_client_message_id)
  returning * into v_message;

  return v_message;
end;
$$;

create or replace function public.messaging_mark_conversation_read(
  p_conversation_id uuid,
  p_through_sequence bigint
)
returns public.messaging_conversation_participants
language plpgsql
security definer
set search_path = public
as $$
declare
  v_conversation public.messaging_conversations%rowtype;
  v_membership_id uuid;
  v_participant public.messaging_conversation_participants%rowtype;
  v_safe_sequence bigint;
begin
  select * into v_conversation
  from public.messaging_conversations
  where id = p_conversation_id and archived_at is null;

  if not found or not public.is_active_household_member(v_conversation.household_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;

  v_membership_id := public.messaging_current_membership_id(v_conversation.household_id);
  if v_membership_id is null or not public.messaging_can_access_conversation(p_conversation_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;

  if v_conversation.conversation_type = 'household' then
    perform public.messaging_seed_household_participants(p_conversation_id);
  end if;

  v_safe_sequence := least(greatest(coalesce(p_through_sequence, 0), 0), v_conversation.next_message_sequence - 1);
  update public.messaging_conversation_participants
  set last_read_sequence = greatest(last_read_sequence, v_safe_sequence),
      last_read_at = case when greatest(last_read_sequence, v_safe_sequence) > last_read_sequence then now() else last_read_at end
  where conversation_id = p_conversation_id and membership_id = v_membership_id and left_at is null
  returning * into v_participant;

  if not found then
    raise exception 'messaging_participant_not_found' using errcode = '42501';
  end if;
  return v_participant;
end;
$$;

alter table public.messaging_conversations enable row level security;
alter table public.messaging_conversation_participants enable row level security;
alter table public.messaging_messages enable row level security;

revoke all on public.messaging_conversations, public.messaging_conversation_participants, public.messaging_messages from anon, authenticated;
grant select on public.messaging_conversations, public.messaging_conversation_participants, public.messaging_messages to authenticated;

create policy messaging_conversations_select_authorized
  on public.messaging_conversations for select to authenticated
  using (public.messaging_can_access_conversation(id));

create policy messaging_participants_select_authorized
  on public.messaging_conversation_participants for select to authenticated
  using (public.messaging_can_access_conversation(conversation_id));

create policy messaging_messages_select_authorized
  on public.messaging_messages for select to authenticated
  using (public.messaging_can_access_conversation(conversation_id));

revoke all on function public.messaging_set_updated_at() from public, anon, authenticated;
revoke all on function public.messaging_current_membership_id(uuid) from public, anon;
revoke all on function public.messaging_can_access_conversation(uuid) from public, anon;
revoke all on function public.messaging_seed_household_participants(uuid) from public, anon, authenticated;
revoke all on function public.messaging_ensure_household_conversation(uuid) from public, anon;
revoke all on function public.messaging_ensure_direct_conversation(uuid, uuid) from public, anon;
revoke all on function public.messaging_send_text_message(uuid, text, uuid) from public, anon;
revoke all on function public.messaging_mark_conversation_read(uuid, bigint) from public, anon;

grant execute on function public.messaging_current_membership_id(uuid) to authenticated;
grant execute on function public.messaging_can_access_conversation(uuid) to authenticated;
grant execute on function public.messaging_ensure_household_conversation(uuid) to authenticated;
grant execute on function public.messaging_ensure_direct_conversation(uuid, uuid) to authenticated;
grant execute on function public.messaging_send_text_message(uuid, text, uuid) to authenticated;
grant execute on function public.messaging_mark_conversation_read(uuid, bigint) to authenticated;

-- Required for postgres_changes transport. RLS above still decides every row
-- delivered to a subscriber; the filter is an optimization, never the gate.
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'messaging_messages'
  ) then
    alter publication supabase_realtime add table public.messaging_messages;
  end if;

  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'messaging_conversations'
  ) then
    alter publication supabase_realtime add table public.messaging_conversations;
  end if;
end;
$$;
