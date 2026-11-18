-- H+ V1: immutable household contribution ledger.
-- Planner remains the authority for task lifecycle; this ledger records a
-- single, derived contribution after a task reaches its canonical terminal
-- completion state. No client is ever granted write access.

create table if not exists public.hplus_ledger_entries (
  id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(id) on delete cascade,
  membership_id uuid not null references public.household_members(id) on delete restrict,
  event_type text not null check (event_type in ('task_completed')),
  source_type text not null check (source_type in ('planner_task')),
  source_id uuid not null,
  points smallint not null check (points in (5, 10, 20)),
  occurred_at timestamptz not null,
  created_at timestamptz not null default now(),
  idempotency_key text not null check (length(btrim(idempotency_key)) between 1 and 200),
  metadata jsonb not null default '{}'::jsonb,
  metadata_version smallint not null default 1 check (metadata_version >= 1),
  unique (idempotency_key),
  unique (household_id, event_type, source_type, source_id)
);

create index if not exists hplus_ledger_household_member_time_idx
  on public.hplus_ledger_entries (household_id, membership_id, occurred_at desc);
create index if not exists hplus_ledger_household_time_idx
  on public.hplus_ledger_entries (household_id, occurred_at desc);

-- Corrections are future compensating entries, never rewrites to history.
create or replace function public.hplus_ledger_immutable()
returns trigger language plpgsql set search_path = public as $$
begin
  raise exception 'hplus_ledger_is_immutable' using errcode = '42501';
end;
$$;
drop trigger if exists hplus_ledger_no_update on public.hplus_ledger_entries;
create trigger hplus_ledger_no_update before update or delete on public.hplus_ledger_entries
for each row execute procedure public.hplus_ledger_immutable();

-- V1 effort policy reuses Planner's existing canonical duration. It is a
-- deliberately small mapping rather than a second task-difficulty model.
create or replace function public.hplus_task_points(p_duration_minutes integer)
returns smallint language sql immutable set search_path = public as $$
  select case
    when coalesce(p_duration_minutes, 0) <= 15 then 5
    when p_duration_minutes <= 60 then 10
    else 20
  end::smallint
$$;

create or replace function public.award_hplus_task_completed(p_task_id uuid)
returns public.hplus_ledger_entries
language plpgsql security definer set search_path = public as $$
declare
  v_task public.planner_tasks%rowtype;
  v_entry public.hplus_ledger_entries%rowtype;
begin
  select * into v_task from public.planner_tasks where id = p_task_id;
  if not found or v_task.status not in ('completed', 'verified')
    or v_task.completed_by_member_id is null then
    raise exception 'hplus_task_completion_not_canonical' using errcode = 'P0001';
  end if;

  -- Membership/household relation is derived from Planner, never caller input.
  if not exists (
    select 1 from public.household_members hm
    where hm.id = v_task.completed_by_member_id
      and hm.household_id = v_task.household_id
  ) then
    raise exception 'hplus_task_actor_invalid' using errcode = '42501';
  end if;

  insert into public.hplus_ledger_entries (
    household_id, membership_id, event_type, source_type, source_id, points,
    occurred_at, idempotency_key, metadata
  ) values (
    v_task.household_id, v_task.completed_by_member_id, 'task_completed',
    'planner_task', v_task.id, public.hplus_task_points(v_task.estimated_duration_minutes),
    coalesce(v_task.completed_at, now()), 'task_completed:' || v_task.id::text,
    jsonb_build_object('planner_status', v_task.status, 'policy_version', 1)
  ) on conflict (idempotency_key) do nothing
  returning * into v_entry;

  if v_entry.id is null then
    select * into v_entry from public.hplus_ledger_entries
    where idempotency_key = 'task_completed:' || v_task.id::text;
  end if;
  return v_entry;
end;
$$;

create or replace function public.hplus_award_task_completed_after_transition()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if new.status in ('completed', 'verified')
    and old.status not in ('completed', 'verified') then
    perform public.award_hplus_task_completed(new.id);
  end if;
  return new;
end;
$$;
drop trigger if exists hplus_award_task_completed on public.planner_tasks;
create trigger hplus_award_task_completed
after update of status on public.planner_tasks
for each row execute procedure public.hplus_award_task_completed_after_transition();

alter table public.hplus_ledger_entries enable row level security;
revoke all on public.hplus_ledger_entries from anon, authenticated;
grant select on public.hplus_ledger_entries to authenticated;
create policy hplus_ledger_select_household_member on public.hplus_ledger_entries
  for select to authenticated using (public.is_active_household_member(household_id));

-- Totals are a full ledger derivation, not a mutable balance or a bounded
-- recent-history approximation. Household and membership remain auth-bound.
create or replace function public.hplus_get_summary(p_household_id uuid)
returns table (my_points bigint, household_points bigint)
language sql stable security definer set search_path = public as $$
  select
    coalesce(sum(case when membership_id = public.messaging_current_membership_id(p_household_id) then points else 0 end), 0)::bigint,
    coalesce(sum(points), 0)::bigint
  from public.hplus_ledger_entries
  where household_id = p_household_id
    and public.is_active_household_member(p_household_id)
$$;

revoke all on function public.hplus_ledger_immutable() from public, anon, authenticated;
revoke all on function public.hplus_task_points(integer) from public, anon, authenticated;
revoke all on function public.award_hplus_task_completed(uuid) from public, anon, authenticated;
revoke all on function public.hplus_award_task_completed_after_transition() from public, anon, authenticated;
revoke all on function public.hplus_get_summary(uuid) from public, anon;
grant execute on function public.hplus_get_summary(uuid) to authenticated;

-- The trigger is the only award writer. The read API is server-shaped.
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public'
      and tablename = 'hplus_ledger_entries'
  ) then
    alter publication supabase_realtime add table public.hplus_ledger_entries;
  end if;
end;

-- Social V1: a member may hold one emoji reaction per message. Reactions are
-- intentionally independent of H+ and never award points.
create table if not exists public.messaging_message_reactions (
  message_id uuid not null references public.messaging_messages(id) on delete cascade,
  membership_id uuid not null references public.household_members(id) on delete cascade,
  reaction_type text not null check (reaction_type in ('like', 'thanks', 'acknowledge')),
  created_at timestamptz not null default now(),
  primary key (message_id, membership_id)
);
create index if not exists messaging_message_reactions_message_idx
  on public.messaging_message_reactions (message_id, reaction_type);

create or replace function public.messaging_toggle_reaction(
  p_message_id uuid, p_reaction_type text
)
returns text language plpgsql security definer set search_path = public as $$
declare
  v_conversation_id uuid;
  v_household_id uuid;
  v_membership_id uuid;
  v_current text;
begin
  select m.conversation_id, c.household_id into v_conversation_id, v_household_id
  from public.messaging_messages m join public.messaging_conversations c on c.id = m.conversation_id
  where m.id = p_message_id and m.deleted_at is null and c.archived_at is null;
  if not found or not public.messaging_can_access_conversation(v_conversation_id) then
    raise exception 'messaging_forbidden' using errcode = '42501';
  end if;
  v_membership_id := public.messaging_current_membership_id(v_household_id);
  if v_membership_id is null or p_reaction_type not in ('like','thanks','acknowledge') then
    raise exception 'messaging_invalid_reaction' using errcode = '22023';
  end if;
  select reaction_type into v_current from public.messaging_message_reactions
  where message_id = p_message_id and membership_id = v_membership_id for update;
  if v_current = p_reaction_type then
    delete from public.messaging_message_reactions where message_id = p_message_id and membership_id = v_membership_id;
    return 'removed';
  end if;
  insert into public.messaging_message_reactions(message_id, membership_id, reaction_type)
  values (p_message_id, v_membership_id, p_reaction_type)
  on conflict (message_id, membership_id) do update set reaction_type = excluded.reaction_type, created_at = now();
  return 'set';
end;
$$;

alter table public.messaging_message_reactions enable row level security;
revoke all on public.messaging_message_reactions from anon, authenticated;
grant select on public.messaging_message_reactions to authenticated;
create policy messaging_reactions_select_authorized on public.messaging_message_reactions
  for select to authenticated using (
    exists (select 1 from public.messaging_messages m where m.id = message_id and public.messaging_can_access_conversation(m.conversation_id))
  );
revoke all on function public.messaging_toggle_reaction(uuid, text) from public, anon;
grant execute on function public.messaging_toggle_reaction(uuid, text) to authenticated;

do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public'
      and tablename = 'messaging_message_reactions'
  ) then
    alter publication supabase_realtime add table public.messaging_message_reactions;
  end if;
end;
