-- Private HOMI-D attachment metadata. Files remain in HOMI-D's private store.
create schema if not exists homi;

create table if not exists homi.attachments (
  attachment_id text primary key,
  household_id text not null,
  owner_id text not null,
  conversation_id text,
  turn_id text,
  storage_path text not null,
  original_filename text not null,
  mime_type text not null,
  size_bytes integer not null check (size_bytes >= 0),
  sha256 text not null,
  status text not null,
  created_at timestamptz not null,
  expires_at timestamptz,
  see_result_id text,
  see_task text
);

create index if not exists homi_attachments_scope_idx
  on homi.attachments (household_id, owner_id, conversation_id, created_at desc);

create table if not exists homi.see_results (
  see_result_id text primary key,
  attachment_id text not null references homi.attachments(attachment_id) on delete cascade,
  conversation_id text not null,
  turn_id text not null,
  request_id text not null,
  task text not null,
  status text not null,
  artifact_type text,
  result_json jsonb not null,
  created_at timestamptz not null
);

create index if not exists homi_see_results_attachment_idx
  on homi.see_results (attachment_id, created_at desc);
