'use strict';
const crypto = require('crypto');

/**
 * HOMI V1 gateway controllers.
 * Identity and household are ALWAYS derived from the authenticated bearer via
 * getPlannerContext. Client-supplied actor/household claims are never trusted.
 */
const { createHttpError } = require('../lib/httpErrors');
const { getPlannerContext } = require('../services/planner.context.service');
const { allTools, projectForModel, catalogSummary } = require('../homi/v1/catalog');
const { isToolVisible, collectCapabilities } = require('../homi/v1/authority');
const { executeTool } = require('../homi/v1/executor');
const { validateHomiIdentityClaims } = require('../homi/v1/contextContract');

const HOMI_D_BASE_URL = (process.env.HOMI_D_BASE_URL || 'http://127.0.0.1:8001').replace(/\/+$/, '');
const D_TIMEOUT = Number(process.env.HOMI_D_TEXT_TIMEOUT_MS || 120000);
const BODY_FIELDS = Object.freeze(['text', 'conversation_id', 'turn_id', 'x_request_id', 'attachments', 'proposal_action']);

function readBody(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw createHttpError(400, 'Cuerpo inválido.', 'homi_request_invalid');
  }
  const out = {};
  for (const key of BODY_FIELDS) if (body[key] !== undefined) out[key] = body[key];
  if (typeof out.text !== 'string' && !out.proposal_action) {
    throw createHttpError(400, 'Se requiere texto o una acción de propuesta.', 'homi_text_required');
  }
  if (out.proposal_action && !['confirm', 'cancel'].includes(out.proposal_action)) {
    throw createHttpError(400, 'Acción de propuesta inválida.', 'homi_proposal_action_invalid');
  }
  return out;
}

function dHeaders(context, accessToken, extra = {}) {
  return {
    Authorization: `Bearer ${accessToken}`,
    'X-Household-Id': context.householdId,
    'X-Actor-Id': context.personId,
    'Content-Type': 'application/json',
    ...extra,
  };
}

async function forwardToD(path, envelope, context, req) {
  let response;
  try {
    response = await fetch(`${HOMI_D_BASE_URL}${path}`, {
      method: 'POST',
      headers: dHeaders(context, req.accessToken),
      body: JSON.stringify(envelope),
      signal: AbortSignal.timeout(D_TIMEOUT),
    });
  } catch {
    throw createHttpError(502, 'HOMI-D no respondió.', 'homi_d_unavailable');
  }
  const text = await response.text();
  let payload;
  try { payload = text ? JSON.parse(text) : {}; } catch { payload = { raw: text.slice(0, 2000) }; }
  if (!response.ok) {
    throw createHttpError(
      response.status >= 500 ? 502 : response.status,
      'HOMI-D rechazó la solicitud.',
      (payload && payload.error && payload.error.code) || 'homi_d_error'
    );
  }
  return payload;
}

/** GET /api/homi/v1/health */
const health = async (_req, res) => {
  res.json({ ok: true, service: 'homi-v1-gateway', catalog: catalogSummary(), d_base: HOMI_D_BASE_URL });
};

/** GET /api/homi/v1/tools — discovery filtrado por contexto real */
const listTools = async (req, res) => {
  const canonical = await getPlannerContext(req);
  const context = {
    actorId: canonical.personId,
    householdId: canonical.householdId,
    role: canonical.role,
  };
  const tools = allTools()
    .filter((tool) => isToolVisible(tool, canonical, context))
    .map(projectForModel);
  res.json({ tools, capabilities: Array.from(collectCapabilities(canonical).set || []) });
};

/** POST /api/homi/v1/tools/:toolId/invoke */
const invokeTool = async (req, res) => {
  const canonical = await getPlannerContext(req);
  const context = {
    actorId: canonical.personId,
    householdId: canonical.householdId,
    role: canonical.role,
  };
  const toolId = req.params.toolId;
  const args = req.body && typeof req.body === 'object' && !Array.isArray(req.body) ? (req.body.args || req.body) : {};

  // Claims del cliente: afirmaciones validadas, nunca autoridad.
  if (req.body && (req.body.actor_id || req.body.household_id)) {
    try {
      validateHomiIdentityClaims({
        actor_id: req.body.actor_id,
        household_id: req.body.household_id,
      }, context);
    } catch {
      throw createHttpError(403, 'Claims de identidad no coinciden con la sesión.', 'homi_identity_claims_rejected');
    }
  }

  const result = await executeTool({
    toolId,
    args,
    req,
    canonical,
    context,
    proposalId: req.body?.proposal_id,
  });
  res.json(result);
};

/** POST /api/homi/v1/text/turn */
const textTurn = async (req, res) => {
  const canonical = await getPlannerContext(req);
  const body = readBody(req.body);
  const envelope = {
    contract_version: '1.0.0',
    context: {
      conversation_id: body.conversation_id || `conv_${canonical.personId.slice(0, 8)}_${Date.now().toString(36)}`,
      turn_id: body.turn_id || `turn_${Date.now().toString(36)}`,
      actor_id: canonical.personId,
      household_id: canonical.householdId,
      ...(body.x_request_id ? { request_id: body.x_request_id } : {}),
    },
    capability: 'think',
    operation: 'infer_with_tools',
    payload: {
      text: body.text || '',
      ...(body.attachments ? { attachments: body.attachments } : {}),
      ...(body.proposal_action ? { proposal_action: body.proposal_action } : {}),
    },
  };
  const payload = await forwardToD('/invoke', envelope, canonical, req);
  res.json(payload);
};

/** POST /api/homi/v1/voice/transcript — STT puro, sin turno semántico */
const voiceTranscript = async (req, res) => {
  const canonical = await getPlannerContext(req);
  let response;
  try {
    response = await fetch(`${HOMI_D_BASE_URL}/v1/voice/transcript`, {
      method: 'POST',
      headers: dHeaders(canonical, req.accessToken, {
        'Content-Type': req.headers['content-type'] || 'application/octet-stream',
        ...(req.headers['x-request-id'] ? { 'X-Request-Id': req.headers['x-request-id'] } : {}),
      }),
      body: req.body,
      signal: AbortSignal.timeout(D_TIMEOUT),
      // node-fetch/undici aceptan Buffer
      duplex: 'half',
    });
  } catch {
    throw createHttpError(502, 'HOMI-D no respondió al STT.', 'homi_stt_unavailable');
  }
  const text = await response.text();
  let payload;
  try { payload = text ? JSON.parse(text) : {}; } catch { payload = { raw: text.slice(0, 2000) }; }
  if (!response.ok) throw createHttpError(response.status, 'STT rechazó el audio.', 'homi_stt_error');
  res.json(payload);
};

/** Verifica el claim EXECUTING y sus argumentos antes de despachar una WRITE. */
function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

async function verifyExecutingProposal(toolId, proposalId, args, bearer, canonical) {
  const secret = process.env.HOMI_INTERNAL_WRITE_SECRET;
  if (!secret) throw createHttpError(503, 'Seam interno no configurado.', 'homi_internal_write_unavailable');
  const url = `${HOMI_D_BASE_URL}/api/homi/v1/internal/proposals/${encodeURIComponent(proposalId)}`;
  let response;
  try {
    response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${bearer}`,
        'X-Homi-Internal-Write': secret,
        'X-Actor-Id': canonical.personId,
        'X-Household-Id': canonical.householdId,
      },
      signal: AbortSignal.timeout(D_TIMEOUT),
    });
  } catch {
    const e = new Error('homi_proposal_check_unavailable');
    e.code = 'homi_proposal_check_unavailable'; e.statusCode = 502;
    throw e;
  }
  if (!response.ok) {
    const e = new Error('homi_proposal_not_confirmed');
    e.code = 'homi_proposal_not_confirmed'; e.statusCode = 403;
    e.details = { tool_id: toolId, d_status: response.status };
    throw e;
  }
  const payload = await response.json().catch(() => ({}));
  const proposal = payload && payload.proposal;
  if (!proposal || proposal.status !== 'EXECUTING' || proposal.tool_id !== toolId || proposal.proposal_id !== proposalId || !proposal.arguments || typeof proposal.arguments !== 'object' || Array.isArray(proposal.arguments)) {
    const e = new Error('homi_proposal_not_confirmed');
    e.code = 'homi_proposal_not_confirmed'; e.statusCode = 403;
    e.details = { tool_id: toolId, d_status: proposal ? proposal.status : null };
    throw e;
  }
  const digest = crypto.createHash('sha256').update(canonicalJson(proposal.arguments)).digest('hex');
  if (digest !== proposal.args_hash || canonicalJson(args) !== canonicalJson(proposal.arguments)) {
    throw createHttpError(409, 'Argumentos de propuesta desactualizados.', 'homi_stale_confirmation');
  }
  return proposal;
}

/** POST /api/homi/v1/internal/tools/:toolId/execute — seam de escritura con propuesta */
const internalExecute = async (req, res) => {
  const internalSecret = process.env.HOMI_INTERNAL_WRITE_SECRET;
  const provided = req.headers['x-homi-internal-write'];
  if (!internalSecret || typeof provided !== 'string' || provided !== internalSecret) {
    throw createHttpError(403, 'Seam interno no autorizado.', 'homi_internal_write_forbidden');
  }
  const canonical = await getPlannerContext(req);
  const context = {
    actorId: canonical.personId,
    householdId: canonical.householdId,
    role: canonical.role,
  };
  const tool = require('../homi/v1/catalog').getTool(req.params.toolId);
  if (!tool || tool.risk_class === 'R0_READ') {
    throw createHttpError(400, 'Tool de escritura inválida.', 'homi_internal_tool_invalid');
  }
  const body = req.body || {};
  if (!body.proposal_id) throw createHttpError(400, 'Falta proposal_id.', 'homi_proposal_required');

  if (!body.args || typeof body.args !== 'object' || Array.isArray(body.args)) {
    throw createHttpError(400, 'Argumentos inválidos.', 'homi_arguments_invalid');
  }
  const proposal = await verifyExecutingProposal(req.params.toolId, body.proposal_id, body.args, req.accessToken, canonical);

  const result = await executeTool({
    toolId: req.params.toolId,
    args: proposal.arguments,
    req,
    canonical,
    context,
    proposalId: body.proposal_id,
  });
  res.json({ ok: true, tool_id: req.params.toolId, proposal_id: body.proposal_id, result: result.data });
};

module.exports = {
  health, listTools, invokeTool, textTurn, voiceTranscript, internalExecute,
  verifyExecutingProposal,
};
