'use strict';

const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

const screen = read('front/mi-front-limpio/screens/finance/FinanceScreen.tsx');
const overview = read('front/mi-front-limpio/components/finance/ui/FinanceOverviewCards.tsx');
const payments = read('front/mi-front-limpio/components/finance/PaymentsList.tsx');
const paymentSummary = read('front/mi-front-limpio/components/finance/FinanceUpcomingPaymentsSummary.tsx');

test('Finance keeps its canonical three-tab product contract', () => {
  const context = read('front/mi-front-limpio/services/finance/financeContext.ts');
  assert.match(context, /FINANCE_TABS = \['resumen', 'movimientos', 'pagos'\]/);
  assert.match(context, /resumen: 'Inicio'/);
  assert.doesNotMatch(context, /FINANCE_TABS[^\n]*limites/i);
});

test('Finance exposes direct Personal and Familia contexts without a sheet', () => {
  assert.match(screen, /testID="finance-context-selector"/);
  assert.match(screen, /financeContextLabel\(selectedContext, activeHousehold, contextLoading\)/);
  assert.match(screen, /<SegmentedControl[\s\S]*value=\{selectedContext\}[\s\S]*onChange=\{chooseContext\}/);
  assert.match(screen, /value: FINANCE_CONTEXT_TYPES\.PERSONAL, label: 'Personal'/);
  assert.match(screen, /value: FINANCE_CONTEXT_TYPES\.HOUSEHOLD,[\s\S]*label: 'Familia'/);
  assert.doesNotMatch(screen, /contextSelectorVisible/);
});

test('Finance summary implements the approved hero and responsive metric cards', () => {
  assert.match(screen, /<FinanceOverviewCards/);
  assert.match(screen, /<FinanceQuickActions/);
  assert.match(screen, /Empezá registrando tu primer gasto/);
  assert.match(screen, /openNewMovement\('expense'\)/);
  assert.match(screen, /initialOperation=\{newMovementOperation\}/);
  assert.match(overview, /periodLabel.*contextLabel/s);
  assert.match(overview, /balance.*expenses.*income/s);
  assert.match(overview, /fontScale >= 1\.45/);
  assert.match(overview, /accessibilityLabel=/);
});

test('movements expose explicit Todos, search and canonical filters', () => {
  assert.match(screen, /<FilterChip label="Todos"/);
  assert.match(screen, /testID="finance-movement-search"/);
  assert.match(screen, /testID="finance-movement-create"/);
  assert.match(screen, /movementMatchesSearch/);
  assert.match(screen, /MOVEMENT_FILTER_OPTIONS/);
});

test('Finance groups management tools under an explicit organizer surface', () => {
  assert.match(screen, /title="Organizar finanzas"/);
  assert.match(screen, /FinanceAccounts/);
  assert.match(screen, /FinanceCategoryManagement/);
  assert.match(screen, /FinanceSpendingLimitsManagement/);
  assert.match(screen, /FinancePoolManagement/);
});

test('primary and auxiliary Finance reads fail independently', () => {
  assert.match(screen, /Promise\.all\(\[\s*listFinanceMovements\(readOptions\),\s*getFinanceSummary\(readOptions\),?\s*\]\)/s);
  // Pools/limits were deliberately moved to their management destinations.
  // The primary surface must not bring those auxiliary requests back.
  assert.doesNotMatch(screen, /getFinancePoolSummary|getFinanceSpendingLimitProgress/);
  assert.match(screen, /getFinanceAnalysis[\s\S]*\.catch\([\s\S]*setAnalysis\(null\)/);
  assert.match(screen, /Analysis is optional supporting content/);
});

test('payments distinguish overdue content without removing productive flows', () => {
  assert.match(payments, /group\.key === 'overdue'/);
  assert.match(payments, /colors\.danger\.soft/);
  assert.match(payments, /CreditCardActionTile/);
  assert.match(payments, /onCreatePayment/);
  assert.match(payments, /onOpenTrash/);
});

test('Resumen reuses the canonical payment snapshot without a duplicate request', () => {
  assert.match(payments, /onSummaryChange\?\.\(summaryPayments\)/);
  assert.match(screen, /<FinanceUpcomingPaymentsSummary/);
  assert.match(paymentSummary, /Pagos próximos/);
  assert.match(paymentSummary, /SUMMARY_PAYMENT_LIMIT = 3/);
  assert.doesNotMatch(paymentSummary, /listPaymentDues|fetch\(/);
});

test('Finance does not reintroduce the removed central navigation action', () => {
  const navbar = read('front/mi-front-limpio/components/ui/BottomNavigation.tsx');
  assert.doesNotMatch(navbar, /centralAction|centerAction|fabAction/i);
});
