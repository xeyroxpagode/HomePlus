'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const SERVICE = path.join(ROOT, 'backend', 'src', 'services', 'assets.service.js');

const REQUIRED_ASSETS_MIGRATIONS = [
  '20261006000000_assets_core_persistence_v1.sql',
  '20261008000000_assets_idempotency_v1.sql',
  '20261008010000_assets_context_v1.sql',
  '20261010000000_assets_profile_change_v1.sql',
  '20261011000000_assets_records_foundation_v1.sql',
  '20261011010000_assets_idempotency_reserve_race_fix_v1.sql',
  '20261012000000_assets_record_link_unlink_v1.sql',
  '20261013000000_assets_record_correction_renewal_v1.sql',
  '20261013010000_assets_period_correction_timestamp_fix_v1.sql',
  '20261013020000_assets_period_correction_single_signature_v1.sql',
  '20261014000000_assets_record_remove_restore_v1.sql',
  '20261015000000_assets_manual_care_foundation_v1.sql',
  '20261016000000_assets_care_remove_restore_v1.sql',
  '20261017000000_assets_identity_category_v1.sql',
  '20261018000000_assets_lifecycle_archive_v1.sql',
  '20261019000000_assets_trash_restore_v1.sql',
  '20261020000000_household_default_permissions_assets_v1.sql',
  '20261021000000_assets_search_unaccent_v1.sql',
  '20261022000000_planner_events_origin_fields_v1.sql',
  '20261022000001_planner_event_origin_write_v1.sql',
];

test('Assets runtime contract keeps the complete ordered migration set', () => {
  for (const filename of REQUIRED_ASSETS_MIGRATIONS) {
    const migration = path.join(ROOT, 'supabase', 'migrations', filename);
    assert.equal(fs.existsSync(migration), true, `Missing Assets migration: ${filename}`);
    assert.ok(fs.statSync(migration).size > 0, `Empty Assets migration: ${filename}`);
  }
});

test('Assets list preserves the public error contract and logs database evidence privately', () => {
  const source = fs.readFileSync(SERVICE, 'utf8');

  assert.match(source, /assetsPersistenceFailureDetails\(error, 'assets\.list'\)/);
  assert.match(source, /'assets_list_failed'/);
  assert.match(source, /supabase_code/);
  assert.match(source, /supabase_message/);
  assert.match(source, /supabase_hint/);
});
