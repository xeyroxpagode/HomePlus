'use strict';

/**
 * Tests de la verificación del estado de propuesta en el seam de escritura
 * (T-FOUND-05, Pass 2).
 *
 * El seam debe rechazar: sin secreto (403), sin proposal_id (400), propuesta
 * no ejecutable/no existente (403 homi_proposal_not_confirmed), tool_id
 * desigual al path (403), argumentos alterados (409) y D inalcanzable (502).
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

// La cadena de import del controlador carga config/supabase.js, que exige
// SUPABASE_URL + SUPABASE_ANON_KEY al cargar. Aquí usamos stubs vacíos sin
// conexión (nunca se habla a la API en este test).
process.env.SUPABASE_URL ||= 'http://127.0.0.1:56221';
process.env.SUPABASE_ANON_KEY ||= 'anon-key-demo-no-real';
// Secreto hermetic vs el entorno: 'secret' de demostración. El
// origen llama a mejores pruebas; los tests de seam tampoco persiguen el
// entorno productivo.
const DEMO_SECRET = 'secret';
process.env.HOMI_INTERNAL_WRITE_SECRET = DEMO_SECRET;

// Los tests de seam no tocan Supabase: stub getPlannerContext antes de
// cargar el controlador (el destructure del binding ocurre en el require).
const plannerContextSvc = require('../../src/services/planner.context.service');
plannerContextSvc.getPlannerContext = async () => ({
  personId: 'p1', householdId: 'h1', role: 'coordinator', membershipStatus: 'active',
});
const controller = require('../../src/controllers/homiV1.controller');

function makeReq(toolId, { proposalId, bearer = 'b1' } = {}) {
  const req = {
    params: { toolId },
    accessToken: bearer,
    headers: { 'x-homi-internal-write': DEMO_SECRET },
    body: proposalId ? { proposal_id: proposalId, args: {} } : {},
  };
  return req;
}

function withFetch(impl) {
  const prev = globalThis.fetch;
  globalThis.fetch = impl;
  return () => { globalThis.fetch = prev; };
}

test('seam interno: sin secreto → 403 homi_internal_write_forbidden', async () => {
  const prev = process.env.HOMI_INTERNAL_WRITE_SECRET;
  process.env.HOMI_INTERNAL_WRITE_SECRET = '';
  try {
    await controller.internalExecute(
      { params: { toolId: 'planner.tasks.create' }, accessToken: 'b1', headers: {}, body: { proposal_id: 'p1', args: {} } },
      {},
    );
    assert.fail('no lanzó');
  } catch (e) {
    assert.equal(e.code, 'homi_internal_write_forbidden');
    assert.equal(e.statusCode, 403);
  } finally {
    if (prev !== undefined) process.env.HOMI_INTERNAL_WRITE_SECRET = prev;
    else delete process.env.HOMI_INTERNAL_WRITE_SECRET;
  }
});

test('seam interno: write sin proposal_id → 400 homi_proposal_required', async () => {
  await assert.rejects(
    () => controller.internalExecute(
      { params: { toolId: 'planner.tasks.create' }, accessToken: 'b1', headers: { 'x-homi-internal-write': DEMO_SECRET }, body: {} },
      {},
    ),
    (e) => e.code === 'homi_proposal_required' && e.statusCode === 400,
  );
});

test('seam interno: propuesta PROPOSED en D → 403 homi_proposal_not_confirmed (sin ejecución)', async () => {
  const restore = withFetch(async () => new Response(
    JSON.stringify({ proposal: { status: 'PROPOSED', tool_id: 'planner.tasks.create' } }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ));
  try {
    await assert.rejects(
      () => controller.internalExecute(makeReq('planner.tasks.create', { proposalId: 'p1' }), {}),
      (e) => e.code === 'homi_proposal_not_confirmed' && e.statusCode === 403,
    );
  } finally { restore(); }
});

test('seam interno: proposal inexistente en D → 403 homi_proposal_not_confirmed', async () => {
  const restore = withFetch(async () => new Response(
    JSON.stringify({ proposal: null }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ));
  try {
    await assert.rejects(
      () => controller.internalExecute(makeReq('planner.tasks.create', { proposalId: 'p1' }), {}),
      (e) => e.code === 'homi_proposal_not_confirmed',
    );
  } finally { restore(); }
});

test('seam interno: propuesta EXECUTING con args y hash vigente → verifica OK', async () => {
  const args = { title: 'Tarea de prueba' };
  const argsHash = crypto.createHash('sha256').update(JSON.stringify(args)).digest('hex');
  const restore = withFetch(async () => new Response(
    JSON.stringify({ proposal: { proposal_id: 'p1', status: 'EXECUTING', tool_id: 'planner.tasks.create', arguments: args, args_hash: argsHash } }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ));
  try {
    const proposal = await controller.verifyExecutingProposal('planner.tasks.create', 'p1', args, 'b1', { personId: 'p1', householdId: 'h1' });
    assert.equal(proposal.status, 'EXECUTING');
    assert.equal(proposal.tool_id, 'planner.tasks.create');
  } finally { restore(); }
});

test('seam interno: argumentos cambiados después de confirmar → 409 sin dispatch', async () => {
  const args = { title: 'Tarea de prueba' };
  const argsHash = crypto.createHash('sha256').update(JSON.stringify(args)).digest('hex');
  const restore = withFetch(async () => new Response(
    JSON.stringify({ proposal: { proposal_id: 'p1', status: 'EXECUTING', tool_id: 'planner.tasks.create', arguments: args, args_hash: argsHash } }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ));
  try {
    await assert.rejects(
      () => controller.verifyExecutingProposal('planner.tasks.create', 'p1', { title: 'Alterada' }, 'b1', { personId: 'p1', householdId: 'h1' }),
      (e) => e.code === 'homi_stale_confirmation' && e.statusCode === 409,
    );
  } finally { restore(); }
});
