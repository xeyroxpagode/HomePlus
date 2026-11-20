'use strict';

/**
 * HOMI V1 execution boundary.
 *
 * Each tool has a frozen endpoint in the verified catalog. The executor never
 * accepts a URL from the model or the caller: it calls only that endpoint of
 * THIS backend with the original bearer token. The endpoint's middleware and
 * canonical service remain the single authority; this layer only validates
 * shape, re-checks authority, resolves opaque references and correlates.
 */
const crypto = require('crypto');
const { getTool } = require('./catalog');
const { getBinding } = require('./generatedBindings');
const { assertExecutionAuthority } = require('./authority');
const { validateToolArguments } = require('./argumentValidator');

const SELF = process.env.HOMI_SELF_BASE_URL || `http://127.0.0.1:${process.env.PORT || 3100}`;
const TIMEOUT_MS = Number(process.env.HOMI_TOOL_TIMEOUT_MS || 15000);

const REF_FIELDS = {
  task_ref: ['title', 'name', 'display_name'],
  account_ref: ['name', 'display_name'],
  conversation_ref: ['title', 'name', 'display_name'],
  product_ref: ['name', 'display_name'],
  asset_ref: ['name', 'display_name'],
  content_ref: ['display_name', 'name', 'title'],
  member_ref: ['display_name', 'name'],
  folder_ref: ['name', 'display_name'],
  album_ref: ['name', 'display_name'],
  transaction_ref: ['description', 'note', 'title'],
};

function fold(value) {
  return String(value == null ? '' : value)
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[\u0300-\u036f]/g, '')
    .trim();
}

function listEndpointFor(path) {
  const parts = path.split('?')[0].split('/').filter(Boolean);
  const last = parts[parts.length - 1] || '';
  if (last.startsWith(':')) parts.pop();
  return '/' + parts.join('/');
}

function pickCandidate(rows, ref, fields) {
  const target = fold(ref);
  const exact = rows.filter((row) => fields.some((f) => fold(row[f]) === target));
  if (exact.length === 1) return exact[0];
  if (exact.length > 1) return null; // ambiguous: never choose arbitrarily
  const partial = rows.filter((row) => fields.some((f) => fold(row[f]).includes(target)));
  if (partial.length === 1) return partial[0];
  return null;
}

async function resolveRefs(tool, args, bearer) {
  const path = tool.http.path;
  const param = path.match(/:([A-Za-z_][\w]*)/g);
  if (!param || param.length === 0) return { args, resolved: {} };

  const refKeys = Object.keys(args).filter((key) => key.endsWith('_ref'));
  if (refKeys.length === 0) return { args, resolved: {} };

  const resolved = {};
  const next = { ...args };
  const listPath = listEndpointFor(path);

  for (const refKey of refKeys) {
    const ref = args[refKey];
    if (typeof ref !== 'string' || ref.length < 1) continue;
    // If the caller supplied a canonical UUID, verify it by direct GET later.
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(ref);
    if (isUuid) {
      resolved[refKey] = { id: ref, via: 'uuid' };
      continue;
    }
    let response;
    try {
      response = await fetch(`${SELF}${listPath}`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${bearer}`, Accept: 'application/json' },
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch {
      const e = new Error('homi_resource_resolution_unavailable');
      e.code = 'homi_resource_resolution_unavailable';
      e.statusCode = 503;
      throw e;
    }
    if (!response.ok) {
      const e = new Error('homi_resource_resolution_denied');
      e.code = 'homi_resource_resolution_denied';
      e.statusCode = response.status;
      throw e;
    }
    const payload = await response.json();
    const rows = Array.isArray(payload)
      ? payload
      : payload.items || payload.data?.items || payload.tasks || payload.events ||
        payload.goals || payload.accounts || payload.movements || payload.conversations ||
        payload.members || payload.products || payload.albums || payload.folders ||
        payload.contents || payload.memories || payload.plans || [];
    const fields = REF_FIELDS[refKey] || ['name', 'title', 'display_name'];
    const candidate = pickCandidate(Array.isArray(rows) ? rows : [], ref, fields);
    if (!candidate || !candidate.id) {
      const e = new Error('homi_ambiguous_reference');
      e.code = 'homi_ambiguous_reference';
      e.statusCode = 409;
      e.details = { field: refKey, candidates: (Array.isArray(rows) ? rows : []).slice(0, 5).map((r) => ({ id: r.id, label: r.name || r.title || r.display_name })) };
      throw e;
    }
    next[refKey] = candidate.id;
    resolved[refKey] = { id: candidate.id, via: 'authorized_list' };
  }
  return { args: next, resolved };
}

function substitutePath(path, args, resolved, context, canonical, tool) {
  const fromContext = {
    household_id: context && context.householdId,
    person_id: context && context.actorId,
    actor_id: context && context.actorId,
    membership_id: canonical && canonical.membershipId,
  };
  return path.replace(/:([A-Za-z_][\w]*)/g, (_match, name) => {
    const key = `${name}_ref`;
    const entity = tool && typeof tool.entity === 'string' ? tool.entity.replace(/s$/, '') : '';
    const entityRef = entity ? `${entity}_ref` : '';
    const value = args[key] !== undefined ? args[key]
      : args[name] !== undefined ? args[name]
        : name === 'id' && entityRef && args[entityRef] !== undefined ? args[entityRef]
      : fromContext[name];
    if (value === undefined || value === null) {
      const e = new Error('homi_missing_resource');
      e.code = 'homi_missing_resource';
      e.statusCode = 400;
      e.details = { parameter: name };
      throw e;
    }
    return encodeURIComponent(String(value));
  });
}

function idempotencyFor(tool, proposalId, args) {
  if (tool.risk_class === 'R0_READ') return {};
  const seed = `${proposalId || 'no-proposal'}:${JSON.stringify(args)}`;
  const hash = crypto.createHash('sha256').update(seed).digest('hex').slice(0, 32);
  return {
    'X-Mutation-Id': `homi-${hash}`,
    'Idempotency-Key': `homi-${hash}`,
  };
}

function canonicalBodyFor(tool, args) {
  if (tool.tool_id !== 'planner.tasks.create') return args;
  const body = { ...args };
  for (const [source, target] of [['dueDate', 'due_date'], ['dueTime', 'due_time']]) {
    if (Object.hasOwn(body, source)) {
      body[target] = body[source];
      delete body[source];
    }
  }
  return body;
}

function mapError(status, body) {
  const code = (body && body.error && body.error.code) || body?.code;
  const map = {
    400: 'invalid_arguments', 401: 'not_authenticated', 403: 'forbidden_capability',
    404: 'not_found_or_not_authorized', 409: 'conflict', 412: 'version_conflict',
    413: 'payload_too_large', 415: 'unsupported_media_type', 422: 'validation_error',
  };
  return {
    status,
    code: status >= 500 ? 'provider_error_retryable' : (map[status] || code || 'tool_error'),
    retryable: status >= 500,
  };
}

async function executeTool({ toolId, args, req, canonical, context, proposalId }) {
  const tool = getTool(toolId);
  if (!tool) {
    const e = new Error('homi_unknown_tool');
    e.code = 'homi_unknown_tool'; e.statusCode = 400;
    throw e;
  }
  // Registro estático de bindings generado desde el catálogo definitivo.
  // El binding solo describe el endpoint congelado: autoridad sigue siendo el
  // middleware y el servicio canónico; el binding nunca invoca URL arbitraria.
  const binding = getBinding(toolId);
  if (!binding) {
    const e = new Error('homi_tool_unbinded');
    e.code = 'homi_tool_unbinded'; e.statusCode = 400;
    e.details = { tool_id: toolId };
    throw e;
  }
  assertExecutionAuthority(tool, canonical, context);

  let validated;
  try {
    validated = { ...validateToolArguments(tool.input_schema, args) };
  } catch (error) {
    const e = new Error(error?.message || 'invalid_arguments');
    e.code = error?.code || 'invalid_arguments';
    e.statusCode = 400;
    e.details = error?.details || undefined;
    throw e;
  }

  // Finance exige contexto explícito. HOMI opera en el hogar derivado del token
  // y jamás acepta un contexto elegido por el modelo.
  if (tool.domain === 'finance') {
    const financeContext = String(validated.context || 'HOUSEHOLD').toLowerCase();
    delete validated.context;
    // El controlador Finance canónico lee contextType/context_type con valores
    // minúsculos (`personal`/`household`). El contrato HOMI usa MAYÚSCULAS.
    validated.contextType = financeContext;
  }

  const bearer = req.accessToken;
  const { args: resolvedArgs, resolved } = await resolveRefs(tool, validated, bearer);
  const endpoint = substitutePath(tool.http.path, resolvedArgs, resolved, context, canonical, tool);
  const query = tool.http.path.includes('?') ? tool.http.path.split('?')[1] : '';
  let url = `${SELF}${endpoint}${query ? (endpoint.includes('?') ? '&' : '?') + query : ''}`;

  const headers = {
    Authorization: `Bearer ${bearer}`,
    Accept: 'application/json',
    ...idempotencyFor(tool, proposalId, resolvedArgs),
  };
  const method = tool.http.method || 'GET';
  if (method !== 'GET' && method !== 'HEAD') {
    headers['Content-Type'] = 'application/json';
  } else {
    // Los argumentos de lectura viajan como query string. Nunca se envían
    // claves de identidad ni referencias ya resueltas en la ruta.
    const params = new URLSearchParams();
    const readArgs = { ...resolvedArgs };
    // El contrato definitivo expone `query`; el controlador Planner CURRENT
    // conserva `q`. Esta traducción es de transporte, no una autoridad nueva.
    if (toolId === 'planner.tasks.search' && readArgs.query !== undefined) {
      readArgs.q = readArgs.query;
      delete readArgs.query;
    }
    // El alcance de /api/planner/search NO es un claim del modelo: se deriva
    // del token. Descartar un `context` no soportado evita un 400 y evita que
    // un valor arbitrario intente alterar el alcance del servicio canónico.
    if (toolId === 'planner.tasks.search' && readArgs.context !== 'active') {
      delete readArgs.context;
    }
    for (const [key, value] of Object.entries(readArgs)) {
      if (key.endsWith('_ref') || value === undefined || value === null) continue;
      if (typeof value === 'object') continue;
      params.set(key, String(value));
    }
    const qs = params.toString();
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: method === 'GET' || method === 'HEAD' ? undefined : JSON.stringify(canonicalBodyFor(tool, resolvedArgs)),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    const e = new Error('homi_provider_timeout');
    e.code = 'homi_provider_timeout'; e.statusCode = 504; e.retryable = true;
    throw e;
  }

  const text = await response.text();
  let body;
  try { body = text ? JSON.parse(text) : {}; } catch { body = { raw: text.slice(0, 2000) }; }

  if (!response.ok) {
    const mapped = mapError(response.status, body);
    const e = new Error(mapped.code);
    e.code = mapped.code; e.statusCode = mapped.status; e.retryable = mapped.retryable;
    e.details = body?.error?.details || undefined;
    throw e;
  }

  return Object.freeze({
    tool_id: toolId,
    data: body,
    meta: {
      endpoint: `${method} ${tool.http.path}`,
      resource_resolution: resolved,
      idempotency_headers: Object.keys(idempotencyFor(tool, proposalId, resolvedArgs)),
      truncated: false,
      omitted_count: 0,
    },
  });
}

module.exports = { executeTool, resolveRefs, mapError };

