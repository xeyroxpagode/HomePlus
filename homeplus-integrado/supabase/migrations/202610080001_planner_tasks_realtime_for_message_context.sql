-- Phase 6: the shared Planner cache needs one household-scoped realtime source.
-- The table is added idempotently because some environments may already expose it.
do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'planner_tasks'
  ) then
    alter publication supabase_realtime add table public.planner_tasks;
  end if;
end;
$$;
