-- Sprint M2: private, household-scoped messaging media.
-- Attachments are binary custody only; HomeCloud files remain a distinct
-- domain and Planner remains the authority for Tasks.

create table if not exists public.messaging_attachments (
  id uuid primary key default gen_random_uuid(),
  message_id uuid unique null references public.messaging_messages(id) on delete set null,
  household_id uuid not null references public.households(id) on delete cascade,
  conversation_id uuid not null references public.messaging_conversations(id) on delete cascade,
  created_by_membership_id uuid not null references public.household_members(id) on delete restrict,
  client_attachment_id uuid not null,
  attachment_kind text not null check (attachment_kind in ('image', 'audio', 'file')),
  mime_type text not null,
  original_name text not null check (length(btrim(original_name)) between 1 and 180),
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 52428800),
  width integer null check (width is null or width > 0),
  height integer null check (height is null or height > 0),
  duration_ms integer null check (duration_ms is null or duration_ms >= 0),
  storage_bucket text not null default 'messaging-attachments',
  storage_path text not null unique,
  lifecycle text not null default 'uploading' check (lifecycle in ('uploading', 'uploaded', 'committed', 'failed')),
  created_at timestamptz not null default now(),
  uploaded_at timestamptz null,
  committed_at timestamptz null,
  metadata jsonb not null default '{}'::jsonb,
  unique (conversation_id, created_by_membership_id, client_attachment_id),
  constraint messaging_attachment_conversation_household_check check (storage_path like (household_id::text || '/%')),
  constraint messaging_attachment_mime_check check (
    (attachment_kind = 'image' and mime_type in ('image/jpeg','image/png','image/webp'))
    or (attachment_kind = 'audio' and mime_type in ('audio/m4a','audio/mp4','audio/mpeg','audio/ogg','audio/wav'))
    or (attachment_kind = 'file' and mime_type in ('application/pdf','text/plain','application/msword','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.ms-excel','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
  )
);

create index if not exists messaging_attachments_message_idx on public.messaging_attachments(message_id) where message_id is not null;
create index if not exists messaging_attachments_conversation_idx on public.messaging_attachments(conversation_id, created_at desc);
create index if not exists messaging_attachments_uncommitted_cleanup_idx on public.messaging_attachments(created_at) where message_id is null and lifecycle in ('uploading', 'uploaded', 'failed');

-- A non-authoritative provenance link: Planner owns the Task, this merely
-- explains which message initiated it and leaves room for future action kinds.
create table if not exists public.messaging_message_actions (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messaging_messages(id) on delete cascade,
  household_id uuid not null references public.households(id) on delete cascade,
  conversation_id uuid not null references public.messaging_conversations(id) on delete cascade,
  created_by_membership_id uuid not null references public.household_members(id) on delete restrict,
  action_type text not null check (action_type in ('task')),
  entity_id uuid not null references public.planner_tasks(id) on delete restrict,
  created_at timestamptz not null default now(),
  unique (message_id, action_type)
);
alter table public.messaging_message_actions enable row level security;
revoke all on public.messaging_message_actions from anon, authenticated;
grant select on public.messaging_message_actions to authenticated;
create policy messaging_message_actions_select_authorized on public.messaging_message_actions
  for select to authenticated using (public.messaging_can_access_conversation(conversation_id));

create or replace function public.messaging_message_action_integrity()
returns trigger language plpgsql security definer set search_path = public as $$
declare v_conversation_id uuid; v_household_id uuid;
begin
  select conversation_id into v_conversation_id from public.messaging_messages where id = new.message_id;
  select household_id into v_household_id from public.messaging_conversations where id = new.conversation_id;
  if v_conversation_id is null or v_conversation_id <> new.conversation_id or v_household_id <> new.household_id then raise exception 'messaging_action_conversation_mismatch' using errcode = '42501'; end if;
  if not exists (select 1 from public.planner_tasks where id = new.entity_id and household_id = new.household_id and trashed_at is null) then raise exception 'messaging_action_entity_mismatch' using errcode = '42501'; end if;
  if not exists (select 1 from public.household_members where id = new.created_by_membership_id and household_id = new.household_id and status = 'active') then raise exception 'messaging_action_member_mismatch' using errcode = '42501'; end if;
  return new;
end $$;
create trigger messaging_message_action_integrity_before_write before insert or update on public.messaging_message_actions for each row execute procedure public.messaging_message_action_integrity();

-- Media has no text payload. Keep existing text/task validation strict.
alter table public.messaging_messages drop constraint if exists messaging_messages_payload_check;
alter table public.messaging_messages add constraint messaging_messages_payload_check check (
  (message_type = 'text' and length(btrim(body)) between 1 and 4000 and context_entity_id is null)
  or (message_type = 'task' and body = '' and context_entity_id is not null)
  or (message_type in ('image', 'audio', 'file') and body = '' and context_entity_id is null)
);
alter table public.messaging_messages drop constraint if exists messaging_messages_type_check;
alter table public.messaging_messages add constraint messaging_messages_type_check check (message_type in ('text', 'task', 'image', 'audio', 'file'));

alter table public.messaging_attachments enable row level security;
revoke all on public.messaging_attachments from anon, authenticated;
grant select on public.messaging_attachments to authenticated;
create policy messaging_attachments_select_authorized on public.messaging_attachments
  for select to authenticated using (public.messaging_can_access_conversation(conversation_id));

create or replace function public.messaging_attachment_integrity()
returns trigger language plpgsql security definer set search_path = public as $$
declare v_household_id uuid;
begin
  select household_id into v_household_id from public.messaging_conversations where id = new.conversation_id;
  if v_household_id is null or v_household_id <> new.household_id then raise exception 'messaging_attachment_conversation_mismatch' using errcode = '42501'; end if;
  if not exists (select 1 from public.household_members where id = new.created_by_membership_id and household_id = new.household_id and status = 'active') then raise exception 'messaging_attachment_member_mismatch' using errcode = '42501'; end if;
  if new.storage_bucket <> 'messaging-attachments' or new.storage_path <> format('%s/messages/%s/%s', new.household_id, new.conversation_id, new.id) then raise exception 'messaging_attachment_storage_path_invalid' using errcode = '22023'; end if;
  return new;
end $$;
create trigger messaging_attachment_integrity_before_write before insert or update on public.messaging_attachments for each row execute procedure public.messaging_attachment_integrity();

-- Clients never get broad Storage access. The backend validates the row and
-- gives one short-lived signed URL for its canonical path.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('messaging-attachments', 'messaging-attachments', false, 52428800,
  array['image/jpeg','image/png','image/webp','audio/m4a','audio/mp4','audio/mpeg','audio/ogg','audio/wav','application/pdf','text/plain','application/msword','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.ms-excel','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;
-- No authenticated/anon Storage policy is created for this bucket. Reads and
-- writes are only via server-issued signed URLs after attachment validation.
drop policy if exists "messaging_attachments_service_full" on storage.objects;
create policy "messaging_attachments_service_full" on storage.objects for all to service_role
  using (bucket_id = 'messaging-attachments') with check (bucket_id = 'messaging-attachments');

create or replace function public.messaging_send_attachment_message(
  p_conversation_id uuid,
  p_attachment_id uuid,
  p_client_message_id uuid
)
returns public.messaging_messages
language plpgsql security definer set search_path = public as $$
declare
  v_conversation public.messaging_conversations%rowtype;
  v_sender uuid;
  v_attachment public.messaging_attachments%rowtype;
  v_existing public.messaging_messages%rowtype;
  v_message public.messaging_messages%rowtype;
  v_sequence bigint;
  v_preview text;
begin
  select * into v_conversation from public.messaging_conversations
  where id = p_conversation_id and archived_at is null for update;
  if not found or not public.is_active_household_member(v_conversation.household_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;
  v_sender := public.messaging_current_membership_id(v_conversation.household_id);
  if v_sender is null or not public.messaging_can_access_conversation(p_conversation_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;
  if v_conversation.conversation_type = 'direct' and not exists (
    select 1 from public.messaging_conversation_participants cp where cp.conversation_id = p_conversation_id and cp.membership_id = v_sender and cp.left_at is null
  ) then raise exception 'messaging_forbidden' using errcode = '42501'; end if;
  if v_conversation.conversation_type = 'household' then perform public.messaging_seed_household_participants(p_conversation_id); end if;
  select * into v_existing from public.messaging_messages where conversation_id = p_conversation_id and sender_membership_id = v_sender and client_message_id = p_client_message_id;
  if found then return v_existing; end if;
  select * into v_attachment from public.messaging_attachments
  where id = p_attachment_id and household_id = v_conversation.household_id and conversation_id = p_conversation_id and created_by_membership_id = v_sender for update;
  if not found then raise exception 'messaging_attachment_not_found' using errcode = 'P0002'; end if;
  if v_attachment.lifecycle <> 'uploaded' or v_attachment.message_id is not null then raise exception 'messaging_attachment_not_ready' using errcode = '22023'; end if;
  v_sequence := v_conversation.next_message_sequence;
  v_preview := case v_attachment.attachment_kind when 'image' then 'Foto enviada' when 'audio' then 'Audio enviado' else 'Archivo adjunto' end;
  update public.messaging_conversations set next_message_sequence = v_sequence + 1, last_message_at = now(), last_message_preview = v_preview, last_message_sender_membership_id = v_sender where id = p_conversation_id;
  insert into public.messaging_messages (conversation_id, sender_membership_id, sequence, message_type, body, client_message_id)
  values (p_conversation_id, v_sender, v_sequence, v_attachment.attachment_kind, '', p_client_message_id) returning * into v_message;
  update public.messaging_attachments set message_id = v_message.id, lifecycle = 'committed', committed_at = now() where id = v_attachment.id;
  return v_message;
end;
$$;
revoke all on function public.messaging_send_attachment_message(uuid, uuid, uuid) from public, anon;
grant execute on function public.messaging_send_attachment_message(uuid, uuid, uuid) to authenticated;

do $$ begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'messaging_attachments') then
    alter publication supabase_realtime add table public.messaging_attachments;
  end if;
end $$;
