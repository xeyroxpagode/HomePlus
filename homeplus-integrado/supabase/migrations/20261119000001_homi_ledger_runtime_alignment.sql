-- Align a previously applied HOMI ledger with the verification lifecycle.
-- Safe for existing runs: all new columns are nullable and every existing
-- status remains valid. This migration never modifies product data or RLS.
alter table homi.execution_runs
  add column if not exists result_code text;

alter table homi.execution_steps
  add column if not exists task_id text;

alter table homi.execution_runs
  drop constraint if exists execution_runs_status_check;

alter table homi.execution_runs
  add constraint execution_runs_status_check
  check (status in (
    'PROPOSED', 'CONFIRMED', 'EXECUTING', 'VERIFYING', 'VERIFIED',
    'SUCCEEDED', 'PARTIAL', 'FAILED', 'EXPIRED', 'CANCELLED'
  ));
