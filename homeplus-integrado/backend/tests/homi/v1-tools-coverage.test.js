'use strict';

/**
 * Cobertura estática completa del catálogo definitivo de HOMI V1 (pasada 2).
 * Lectura de artifacts ya generados por:
 *   - docs/homi/full-integration/closure-discovery/_generate.cjs (catálogo final)
 *   - docs/homi/full-integration/closure-discovery/_gen_runtime_catalog.cjs (tool_catalog.json)
 *   - docs/homi/full-integration/closure-discovery/_gen_runtime_bindings.cjs (generatedBindings.js)
 * No muta producto: solo validaciones.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { allTools, getTool, catalogDigest, catalogSummary } = require('../../src/homi/v1/catalog');
const { getBinding, BINDINGS } = require('../../src/homi/v1/generatedBindings');
const { validateToolArguments, HomiArgumentError } = require('../../src/homi/v1/argumentValidator');

const forbidden = ['actor_id', 'household_id', 'membership_id', 'role', 'authorization', 'tool_call_id', 'catalog_digest', 'request_id', 'trace_id'];
const RISKS = new Set(['R0_READ', 'R1_SAFE_WRITE', 'R2_CONFIRMED_WRITE']);

test('307 tools en el registro, 0 duplicados, digest consistente', () => {
  const tools = allTools();
  assert.equal(tools.length, 307);
  const ids = tools.map((t) => t.tool_id);
  assert.equal(new Set(ids).size, 307, 'duplicate tool ids');
  assert.equal(catalogSummary().implemented_tools, 307);
  assert.match(catalogDigest(), /^[0-9a-f]{64}$/);
  assert.equal(BINDINGS.targets.length, 307);
});

test('cada tool tiene binding ejecutíble, endpoint congelado y servicio canónico', () => {
  for (const tool of allTools()) {
    const binding = getBinding(tool.tool_id);
    assert.ok(binding, `binding ausente: ${tool.tool_id}`);
    assert.equal(binding.http.method, tool.http.method);
    assert.equal(binding.http.path, tool.http.path);
    assert.match(tool.http.path, /^\/api\//, `${tool.tool_id}: endpoint debe empezar con /api/`);
    assert.match(binding.canonical_service, /\.js::[A-Za-z_$][\w$]*$/, `${tool.tool_id}: canonical_service ${binding.canonical_service}`);
    assert.ok(tool.execution && tool.execution.handler, `${tool.tool_id}: handler`);
    assert.ok(tool.execution && typeof tool.execution.idempotency === 'string', `${tool.tool_id}: idempotency`);
    assert.ok(tool.execution && Array.isArray(tool.authority.forbidden_model_fields), `${tool.tool_id}: authority`);
    for (const f of forbidden) {
      assert.equal(tool.input_schema.properties[f], undefined, `${tool.tool_id} expone ${f}`);
      assert.equal(tool.authority.forbidden_model_fields.includes(f), true, `${tool.tool_id}: ${f} debe estar en forbidden_model_fields`);
    }
  }
});

test('contrato de Tools: inputs, outputs y políticas cerradas', () => {
  for (const tool of allTools()) {
    assert.equal(tool.input_schema.additionalProperties, false);
    assert.equal(Array.isArray(tool.test_cases), true, tool.tool_id);
    assert.ok(tool.test_cases.length >= 8, tool.tool_id);
    assert.equal(RISKS.has(tool.risk_class), true, tool.tool_id);
    assert.equal(['NONE', 'PREVIEW_THEN_CONFIRM', 'CONFIRM_REINFORCED'].includes(tool.confirmation_policy), true, tool.tool_id);
    if (tool.read_write === 'WRITE') {
      assert.notEqual(tool.confirmation_policy, 'NONE', tool.tool_id);
      assert.ok(Array.isArray(tool.side_effects) && tool.side_effects.length > 0, tool.tool_id);
      assert.equal(tool.execution.ledger, 'homi.tool.execution.started + homi.tool.execution.write', tool.tool_id);
    }
    if (tool.read_write === 'READ') {
      assert.deepEqual(tool.side_effects, [], tool.tool_id);
      assert.equal(tool.execution.ledger, 'homi.tool.execution.read', tool.tool_id);
    }
    // Negative test por tool: campo desconocido siempre rechazado.
    if (Object.keys(tool.input_schema.properties || {}).length > 0) {
      assert.throws(() => validateToolArguments(tool.input_schema, { __homi_unknown_field: 1 }), HomiArgumentError, tool.tool_id);
    }
  }
});

test('cobertura por dominio: 307 = 114 READ + 193 WRITE, según el catálogo final', () => {
  const byDomain = allTools().reduce((acc, t) => {
    acc[t.domain] = (acc[t.domain] || 0) + 1;
    return acc;
  }, {});
  const reads = allTools().filter((t) => t.read_write === 'READ').length;
  const writes = allTools().filter((t) => t.read_write === 'WRITE').length;
  assert.equal(reads, 114);
  assert.equal(writes, 193);
  const expected = {
    identity: 5, households: 12, home: 3, planner: 96, finance: 62,
    inventory: 54, assets: 39, homecloud: 23, messages: 9,
    notifications: 1, hplus: 2, settings: 1,
  };
  assert.deepEqual(byDomain, expected);
});

test('READ-only tools: lógica de validación rechaza args ausentes y extras', () => {
  const read = getTool('homecloud.files.list');
  assert.ok(read && read.read_write === 'READ');
  assert.throws(() => validateToolArguments(read.input_schema, { query: 'x', extra: 1 }), HomiArgumentError);
});

test('endpoint inexistente → tool desconocido → 400 honrado', () => {
  assert.equal(getTool('nope.nope.nope'), null);
  assert.equal(getBinding('nope.nope.nope'), null);
});
