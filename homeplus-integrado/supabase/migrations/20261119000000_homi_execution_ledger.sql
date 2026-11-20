-- HOMI V1 — execution ledger
-- Migración NUEVA y NO DESTRUCTIVA. No toca tablas de producto ni RLS existente.
-- Motivo: el contrato de ejecución HOMI (propuestas, idempotencia, recovery)
-- exige persistencia durable. El DDL anterior no estaba versionado.
-- Reversión segura en entorno de pruebas: DROP SCHEMA homi CASCADE;
-- En producción requiere autorización explícita (no se ejecuta en esta entrega).

create schema if not exists homi;

revoke all on schema homi from public;
grant usage on schema homi to authenticated;

create table if not exists homi.execution_runs (
  id                    uuid primary key default gen_random_uuid(),
  proposal_id           text not null,
  conversation_id       text,
  tool_id               text not null,
  status                text not null check (status in ('PROPOSED','CONFIRMED','EXECUTING','VERIFYING','VERIFIED','SUCCEEDED','PARTIAL','FAILED','EXPIRED','CANCELLED')),
  proposal_snapshot     jsonb not null default '{}'::jsonb,
  payload_hash          text not null,
  actor_ref             text not null,
  scope_ref             text not null,
  execution_id          text,
  idempotency_key       text,
  result_json           jsonb,
  result_code           text,
  reason                text,
  outcome_uncertain     boolean not null default false,
  confirmed_at          timestamptz,
  expires_at            timestamptz,
  started_at            timestamptz,
  completed_at          timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

create unique index if not exists execution_runs_proposal_uq
  on homi.execution_runs (proposal_id);

create index if not exists execution_runs_conversation_idx
  on homi.execution_runs (conversation_id, created_at desc);

create table if not exists homi.execution_steps (
  id                    uuid primary key default gen_random_uuid(),
  run_id                uuid not null references homi.execution_runs (id) on delete cascade,
  proposal_id           text not null,
  operation_index       integer not null,
  status                text not null check (status in ('PENDING','SUCCEEDED','FAILED','UNKNOWN')),
  idempotency_key       text,
  mutation_id           text,
  task_id               text,
  error_code            text,
  error_status          integer,
  updated_at            timestamptz not null default now(),
  unique (proposal_id, operation_index)
);

create index if not exists execution_steps_run_idx
  on homi.execution_steps (run_id, operation_index);

-- Las filas se insertan ANTES de despachar la escritura (fail-before-commit).
-- No se crea ninguna tabla en public., no se altera RLS y no se concede
-- acceso a datos privados de otros usuarios.
