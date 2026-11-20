'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { allTools, catalogSummary, catalogDigest, getTool } = require('../../src/homi/v1/catalog');
const { isToolVisible } = require('../../src/homi/v1/authority');
const fs = require('node:fs');
const path = require('node:path');
const { validateToolArguments } = require('../../src/homi/v1/argumentValidator');

const FORBIDDEN = ['actor_id', 'household_id', 'membership_id', 'role', 'authorization', 'tool_call_id'];

test('catálogo: 307 tools (114 READ / 193 WRITE) — contrato definitivo de la pasada 2', () => {
  const s = catalogSummary();
  assert.equal(s.implemented_tools, 307);
  assert.equal(s.read_tools, 114);
  assert.equal(s.write_tools, 193);
  assert.equal(allTools().length, 307);
  assert.match(catalogDigest(), /^[0-9a-f]{64}$/);
});

test('Planner task WRITE accepts the canonical dueDate field', () => {
  for (const id of ['planner.tasks.create', 'planner.tasks.update']) {
    const schema = getTool(id).input_schema;
    assert.ok(schema.properties.dueDate, id);
    assert.equal(schema.properties.date, undefined, id);
    assert.doesNotThrow(() => validateToolArguments(schema, { dueDate: '2026-11-20' }));
  }
});

test('Planner list READs preserve canonical status and temporal filters', () => {
  const tasks = getTool('planner.tasks.list').input_schema;
  assert.deepEqual(tasks.properties.status.enum, [
    'pending', 'awaiting_verification', 'verified', 'completed', 'cancelled',
  ]);
  assert.ok(tasks.properties.from);
  assert.ok(tasks.properties.to);
  assert.doesNotThrow(() => validateToolArguments(tasks, {
    status: 'pending', from: '2026-11-20', to: '2026-11-21',
  }));

  const events = getTool('planner.events.list').input_schema;
  assert.deepEqual(events.properties.status.enum, ['scheduled', 'cancelled']);
  assert.ok(events.properties.from);
  assert.ok(events.properties.to);
  assert.doesNotThrow(() => validateToolArguments(events, {
    status: 'scheduled',
    from: '2026-11-20T00:00:00-03:00',
    to: '2026-11-29T23:59:59-03:00',
  }));
});

test('ninguna tool expone campos de identidad al modelo', () => {
  for (const tool of allTools()) {
    const props = Object.keys(tool.input_schema.properties || {});
    for (const field of FORBIDDEN) {
      assert.equal(props.includes(field), false, `${tool.tool_id} expone ${field}`);
    }
    assert.equal(tool.input_schema.additionalProperties, false, tool.tool_id);
  }
});

test('toda tool IMPLEMENT tiene endpoint canónico, riesgo y handler', () => {
  for (const tool of allTools()) {
    assert.ok(tool.http && tool.http.method && tool.http.path, tool.tool_id);
    assert.ok(/\.js::[A-Za-z_$][\w$]*$/.test(tool.canonical_service), `${tool.tool_id}: ${tool.canonical_service}`);
    assert.ok(tool.execution.handler, tool.tool_id);
    assert.ok(tool.risk_class, tool.tool_id);
    assert.ok(Array.isArray(tool.test_cases) && tool.test_cases.length > 0, tool.tool_id);
  }
});

test('escrituras declaran idempotencia y compensación segura', () => {
  const writes = allTools().filter((t) => t.read_write === 'WRITE');
  assert.equal(writes.length, 193);
  for (const tool of writes) {
    assert.match(tool.execution.idempotency, /X-Mutation-Id|Idempotency-Key|proposal_id/, tool.tool_id);
    assert.match(tool.execution.compensation_policy, /No se fabrican|nunca|Reintentos/, tool.tool_id);
    assert.ok(tool.confirmation_policy.includes('CONFIRM'), tool.tool_id);
  }
});

test('lecturas no tienen efectos y registran solo la etapa de lectura', () => {
  for (const tool of allTools().filter((t) => t.read_write === 'READ')) {
    assert.deepEqual(tool.side_effects, [], tool.tool_id);
    assert.equal(tool.execution.ledger, 'homi.tool.execution.read', tool.tool_id);
  }
});

test('feed, credenciales y dispositivo nativo no se exponen como tools', () => {
  for (const id of [
    'feed.posts.list', 'feed.posts.create',
    'identity.register', 'identity.login', 'identity.refresh', 'identity.logout',
    'identity.user-metadata.update',
    'notifications.devices.register',
    'presence.locations.list', 'presence.my-location.update',
  ]) {
    assert.equal(getTool(id), null, id);
  }
});

test('descubrimiento respeta capability y fail-closed sin contexto', () => {
  const tool = getTool('homecloud.files.list');
  const canonical = {
    role: 'coordinator', membershipStatus: 'active',
    household: { id: 'h1', config: {} }, householdId: 'h1',
  };
  const context = { actorId: 'p1', householdId: 'h1', role: 'coordinator' };
  assert.equal(isToolVisible(tool, canonical, context), true);
  assert.equal(isToolVisible(tool, canonical, null), false);
  assert.equal(isToolVisible(tool, null, context), false);
  assert.equal(isToolVisible(null, canonical, context), false);
});

test('migración del ledger existe y es no destructiva', () => {
  const file = path.join(__dirname, '../../../supabase/migrations/20261119000000_homi_execution_ledger.sql');
  const sql = fs.readFileSync(file, 'utf8');
  assert.match(sql, /create schema if not exists homi/);
  assert.match(sql, /create table if not exists homi\.execution_runs/);
  assert.match(sql, /create table if not exists homi\.execution_steps/);
  assert.doesNotMatch(sql, /drop table|truncate|delete from/i);
});
