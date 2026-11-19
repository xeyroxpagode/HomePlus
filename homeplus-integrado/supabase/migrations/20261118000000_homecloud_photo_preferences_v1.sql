-- Additive optional photo preferences. Does not move, delete or rewrite media.
begin;
create table if not exists public.homecloud_album_covers (
  album_id uuid primary key references public.homecloud_albums(id) on delete cascade,
  content_id uuid not null references public.homecloud_contents(id) on delete cascade,
  foreign key (album_id, content_id) references public.homecloud_album_items(album_id, content_id) on delete cascade
);
create table if not exists public.homecloud_memory_favorites (
  account_id uuid not null references auth.users(id) on delete cascade,
  content_id uuid not null references public.homecloud_contents(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (account_id, content_id)
);
create index if not exists homecloud_memory_favorites_content_idx on public.homecloud_memory_favorites(content_id);
-- Same server-only metadata authority as HomeCloud's existing write services.
-- No client SQL access: authenticated API derives household and rechecks capability.
alter table public.homecloud_album_covers enable row level security;
alter table public.homecloud_memory_favorites enable row level security;
revoke all on public.homecloud_album_covers, public.homecloud_memory_favorites from anon, authenticated;
grant select, insert, update, delete on public.homecloud_album_covers, public.homecloud_memory_favorites to service_role;
comment on table public.homecloud_album_covers is 'One existing album member as cover. Removing membership clears the cover, never the photo.';
comment on table public.homecloud_memory_favorites is 'Personal account favorites. Not a household ACL or shared favorite flag.';
commit;
