#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '../../..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
let failed = 0;

function assert(condition, message) {
  if (condition) console.log(`  ok ${message}`);
  else { failed += 1; console.error(`  fail ${message}`); }
}

console.log('=== Task context card contracts ===');

const card = read('front/mi-front-limpio/components/messages/MessageContextCard.tsx');
const bridge = read('front/mi-front-limpio/context/PlannerTaskRealtimeBridge.tsx');
const service = read('backend/src/services/planner.tasks.service.js');
const claimRpc = read('supabase/migrations/20260722020000_m11_1b_task_fulfillment_operations.sql');
const realtimeMigration = read('supabase/migrations/202610080001_planner_tasks_realtime_for_message_context.sql');

assert(card.includes("availableActions.some((action) => action.action === 'claim')"), 'claim CTA follows Planner capability projection');
assert(card.includes('await load();'), 'claim success or conflict reloads canonical Planner state');
assert(bridge.includes("table: 'planner_tasks'") && bridge.includes('markPlannerChanged()'), 'one household-scoped planner signal drives visible cards');
assert(bridge.includes('plannerCache.executeInvalidation'), 'remote task signals invalidate shared Planner cache');
assert(realtimeMigration.includes('alter publication supabase_realtime add table public.planner_tasks'), 'Planner task table is published for shared realtime');

const claimStart = claimRpc.indexOf('create or replace function public.claim_planner_task_v1');
const claimEnd = claimRpc.indexOf('create or replace function public.mutate_planner_task_fulfillment_v1', claimStart);
const claim = claimRpc.slice(claimStart, claimEnd);
assert(claim.includes('for update;'), 'claim serializes contenders with row locks');
assert(claim.includes("'already_claimed'"), 'second contender has a canonical already_claimed outcome');
assert(claim.includes('insert into public.planner_task_assignees'), 'only the winning mutation writes the assignee');
assert(service.includes("data?.outcome === 'already_claimed'") && service.includes('current: current.task'), 'backend returns canonical state to the losing client');

if (failed) process.exit(1);
console.log('TASK CONTEXT CARD CONTRACTS: PASS');
