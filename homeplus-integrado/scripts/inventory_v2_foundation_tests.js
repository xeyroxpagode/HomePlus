'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8');
const requireText = (source, needle, label) => assert.ok(source.includes(needle), `${label}: missing ${needle}`);

const migrations = [
  '20261019000001_inventory_v2_foundation.sql',
  '20261019000002_inventory_v2_atomic_rpc.sql',
  '20261019000003_inventory_v2_products_ui_read_contract.sql',
  '20261020000001_inventory_v2_shopping_purchase_domain.sql',
  '20261020000002_inventory_v2_finance_source_integration.sql',
];

for (const migration of migrations) {
  const source = read('supabase', 'migrations', migration);
  assert.ok(!/drop\s+table\s+(?!if\s+exists\s+inventory_v2_)/i.test(source), `${migration}: may not drop legacy inventory tables`);
}

const foundation = read('supabase', 'migrations', migrations[0]);
requireText(foundation, 'inventory_locations', 'foundation locations');
requireText(foundation, 'alter table public.inventory_items', 'foundation additive V1 product evolution');
requireText(foundation, 'inventory_shopping_lists', 'foundation shopping list');
requireText(foundation, 'inventory_purchase_sessions', 'foundation purchase session');
requireText(foundation, "inventory_has_capability(household_id, 'inventory.view')", 'foundation household capability authority');
requireText(foundation, 'row level security', 'foundation RLS');

const atomic = read('supabase', 'migrations', migrations[1]);
requireText(atomic, 'inventory_adjust_quantity', 'atomic quantity mutation');
requireText(atomic, 'inventory_legacy_log_movement', 'atomic V1 movement adapter');
requireText(atomic, 'idempotency', 'atomic idempotency');
requireText(atomic, 'version_conflict_v2', 'atomic optimistic concurrency');

const shopping = read('supabase', 'migrations', migrations[3]);
requireText(shopping, 'inventory_finalize_purchase', 'purchase finalization RPC');

const route = read('backend', 'src', 'routes', 'inventory.js');
for (const endpoint of ['/shopping-list', '/purchases/start', '/products', '/items', '/restock-requests']) {
  requireText(route, endpoint, 'inventory route preservation');
}

const contracts = read('backend', 'src', 'lib', 'mutationContracts.js');
requireText(contracts, "IDEMPOTENT_MUTATION: 'IDEMPOTENT_MUTATION'", 'backend mutation contract');
const legacyService = read('backend', 'src', 'services', 'inventory.service.js');
requireText(legacyService, "rpc('inventory_legacy_log_movement'", 'legacy V1 adapter');

const controller = read('backend', 'src', 'inventory', 'inventory.controller.js');
requireText(controller, 'getHouseholdRequestContext', 'v2 context authority');
requireText(controller, 'OPERATION_KINDS.VERSIONED_MUTATION', 'v2 versioned mutations');
requireText(controller, 'OPERATION_KINDS.IDEMPOTENT_MUTATION', 'v2 idempotent mutations');

const api = read('front', 'mi-front-limpio', 'services', 'api.ts');
requireText(api, "IDEMPOTENT_MUTATION: 'IDEMPOTENT_MUTATION'", 'frontend mutation contract');
requireText(api, 'operationKind === OPERATION_KINDS.IDEMPOTENT_MUTATION', 'frontend idempotency header behavior');
const client = read('front', 'mi-front-limpio', 'services', 'inventoryV2.ts');
requireText(client, "'/api/inventory/shopping-list'", 'typed shopping client');
requireText(client, "'/api/inventory/products'", 'typed products client');
requireText(client, 'OPERATION_KINDS.VERSIONED_MUTATION', 'typed versioned operations');

console.log('Inventory V2 foundation static contracts: PASS');
