-- HomePlus Inventory Premium V2: READ-ONLY runtime validation.
-- Run AFTER applying these migrations in this exact order:
-- 20261019000001, 20261019000002, 20261019000003,
-- 20261020000001, 20261020000002.
-- This script does not change schema, data, RLS, or migration history.

-- 1) Required V2 tables must exist.
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in (
    'inventory_catalog_items', 'inventory_catalog_aliases',
    'inventory_catalog_household_stats', 'inventory_locations',
    'inventory_shopping_lists', 'inventory_shopping_list_items',
    'inventory_purchase_sessions', 'inventory_purchase_lines',
    'inventory_idempotency_keys', 'finance_transaction_sources'
  )
order by table_name;

-- 2) The V2 extension columns on the existing inventory_items table.
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'inventory_items'
  and column_name in (
    'catalog_item_id', 'location_id', 'notes', 'auto_restock_enabled',
    'target_quantity', 'auto_restock_suppressed', 'archived_at',
    'trashed_at', 'pre_trash_lifecycle', 'version', 'updated_by_person_id'
  )
order by column_name;

-- 3) RLS must be enabled on household-scoped V2 tables.
select relname as table_name, relrowsecurity as rls_enabled
from pg_class
where relnamespace = 'public'::regnamespace
  and relname in (
    'inventory_catalog_items', 'inventory_catalog_aliases',
    'inventory_catalog_household_stats', 'inventory_locations',
    'inventory_shopping_lists', 'inventory_shopping_list_items',
    'inventory_purchase_sessions', 'inventory_purchase_lines',
    'inventory_idempotency_keys', 'finance_transaction_sources'
  )
order by relname;

-- 4) Read policies must be present; server RPCs own writes.
select tablename, policyname, cmd
from pg_policies
where schemaname = 'public'
  and tablename in (
    'inventory_catalog_items', 'inventory_catalog_aliases',
    'inventory_catalog_household_stats', 'inventory_locations',
    'inventory_shopping_lists', 'inventory_shopping_list_items',
    'inventory_purchase_sessions', 'inventory_purchase_lines'
  )
order by tablename, policyname;

-- 5) Integrity and exactly-once indexes must be active.
select indexname, indexdef
from pg_indexes
where schemaname = 'public'
  and indexname in (
    'inventory_locations_household_normalized_name_unique',
    'inventory_shopping_item_active_dedupe_uidx',
    'inventory_purchase_one_open_per_household',
    'inventory_purchase_line_shopping_item_uidx',
    'planner_inventory_shopping_open_uidx'
  )
order by indexname;

-- 6) Canonical RPC authority and auto-list trigger must exist.
select p.proname as function_name
from pg_proc p
where p.pronamespace = 'public'::regnamespace
  and p.proname in (
    'inventory_shopping_list_get', 'inventory_shopping_item_add',
    'inventory_shopping_item_mutate', 'inventory_shopping_clear',
    'inventory_shopping_batch', 'inventory_purchase_start',
    'inventory_finalize_purchase', 'inventory_reconcile_auto_restock',
    'finance_create_inventory_purchase_expense_v1'
  )
order by p.proname;

select tgname as trigger_name, tgrelid::regclass as on_table
from pg_trigger
where not tgisinternal
  and tgname = 'trg_inventory_household_shopping_list';

-- 7) Realtime membership for V2 entities (may be empty until the realtime
-- publication is explicitly configured in the remote project).
select schemaname, tablename
from pg_publication_tables
where pubname = 'supabase_realtime'
  and schemaname = 'public'
  and tablename in (
    'inventory_items', 'inventory_locations', 'inventory_shopping_list_items',
    'inventory_purchase_sessions', 'inventory_purchase_lines'
  )
order by tablename;
