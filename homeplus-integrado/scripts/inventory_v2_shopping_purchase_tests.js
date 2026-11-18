'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8');
const need = (text, expected, label) => assert.ok(text.includes(expected), `${label}: missing ${expected}`);

const shopping = read('backend', 'src', 'inventory', 'shopping', 'shopping.service.js');
need(shopping, "requireCapability(c,'inventory.use')", 'shopping capability');
need(shopping, 'planner', 'shopping Planner integration');
need(shopping, 'idempotencyKey', 'shopping idempotency input');

const purchases = read('backend', 'src', 'inventory', 'purchases', 'purchases.service.js');
need(purchases, "requireCapability(c,'inventory.use')", 'purchase capability');
need(purchases, 'finance_create_inventory_purchase_expense_v1', 'Finance source integration RPC');
need(purchases, 'expectedVersion', 'purchase optimistic concurrency');
need(purchases, 'idempotencyKey', 'purchase idempotency');

const integration = read('backend', 'src', 'inventory', 'integrations', 'index.js');
need(integration, 'task.create_household', 'Planner capability authority');

const legacyInventory = read('backend', 'src', 'services', 'inventory.service.js');
need(legacyInventory, 'closeResolvedRestockRequests', 'legacy restock cleanup after stock recovery');
need(legacyInventory, "outcome: 'restock_not_needed'", 'restock approval re-checks current stock');
need(legacyInventory, 'inventory_shopping_item_add', 'restock approval adds the canonical Shopping item');

const financeSql = read('supabase', 'migrations', '20261020000002_inventory_v2_finance_source_integration.sql');
need(financeSql, 'finance_create_transaction_with_optional_account_effect_v1', 'Finance RPC contract');
need(financeSql, 'finance_create_inventory_purchase_expense_v1', 'purchase-to-finance integration contract');

const client = read('front', 'mi-front-limpio', 'services', 'inventoryV2.ts');
for (const action of ['createInventoryShoppingPlannerTask', 'startInventoryPurchase', 'finalizeInventoryPurchase', 'retryInventoryPurchaseFinance']) {
  need(client, action, 'typed V2 client');
}

const shoppingScreen = read('front', 'mi-front-limpio', 'screens', 'inventory', 'InventoryShoppingListScreen.tsx');
need(shoppingScreen, 'startInventoryPurchase', 'shopping starts or resumes a canonical purchase');
need(shoppingScreen, "navigation.navigate('InventoryPurchase'", 'shopping-to-purchase navigation');
need(shoppingScreen, 'createInventoryShoppingPlannerTask', 'shopping uses the canonical Planner task operation');
need(shoppingScreen, 'getInventoryIntegrations', 'shopping respects the server-derived Planner capability');
need(shoppingScreen, "screen: 'TaskDetail'", 'shopping can open the canonical Planner task detail');
need(shoppingScreen, 'inventory.shopping.createPlannerTask', 'shopping exposes a stable automation target for Planner task creation');
need(shoppingScreen, "source: 'inventory'", 'manual exact-name product can link to Inventory');

const purchaseScreen = read('front', 'mi-front-limpio', 'screens', 'inventory', 'InventoryPurchaseScreen.tsx');
for (const action of ['getInventoryPurchaseDetail', 'setInventoryPurchaseLine', 'finalizeInventoryPurchase', 'retryInventoryPurchaseFinance']) {
  need(purchaseScreen, action, 'purchase screen canonical operation');
}
need(purchaseScreen, 'expectedVersion', 'purchase screen optimistic concurrency');
need(purchaseScreen, 'idempotencyKey', 'purchase screen idempotency');
need(purchaseScreen, 'El stock cambia recién al terminar la compra.', 'purchase screen stock boundary');

const actionSheet = read('front', 'mi-front-limpio', 'components', 'ui', 'ActionSheet.tsx');
need(actionSheet, 'keyboardAware = true', 'temporary forms are keyboard-aware by default');

const navigator = read('front', 'mi-front-limpio', 'navigation', 'HomeTabNavigator.tsx');
need(navigator, 'InventoryPurchase', 'purchase screen registered in navigation');

console.log('Inventory V2 shopping and purchase static contracts: PASS');
