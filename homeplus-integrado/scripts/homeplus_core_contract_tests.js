'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { OPERATION_KINDS, requireMutationContract, assertExpectedVersionMatches } = require('../backend/src/lib/mutationContracts');
const { createCapabilityCatalog, projectCapabilities, hasCapability } = require('../backend/src/lib/capabilityEngine');
const {
  resolveHouseholdCapabilities,
  FINAL_ROLES,
  isFinalRole,
  isFunctionalMembershipStatus,
  isAllMembershipStatus,
  getDefaultHouseholdPermissions,
  canInviteMembers,
  canApproveMembers,
  canRemoveMember,
  canManageRoles,
  canAssignCoordinator,
  canEditConfig,
} = require('../backend/src/lib/householdPermissions');
const { resolveCapabilities } = require('../backend/src/lib/plannerCapabilities');
const { createHttpError, sendError, buildApiErrorEnvelope, sendApiError } = require('../backend/src/lib/httpErrors');
const { legacyBodyToError, errorEnvelopeMiddleware } = require('../backend/src/middleware/errorEnvelopeMiddleware');
const { requestContextMiddleware } = require('../backend/src/middleware/requestContextMiddleware');

const root = path.resolve(__dirname, '..');
let passed = 0;
function assert(condition, message) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  passed += 1;
  console.log(`PASS: ${message}`);
}
function expectCode(fn, code) {
  try { fn(); } catch (error) { return error.code === code; }
  return false;
}
function read(relative) {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

const emptyRequest = { headers: {}, body: {} };
assert(requireMutationContract(emptyRequest, OPERATION_KINDS.READ_ONLY).mutationId === null, 'read-only operations require no mutation headers');
assert(expectCode(() => requireMutationContract(emptyRequest, OPERATION_KINDS.CREATE_IDEMPOTENT), 'mutation_id_required'), 'create operations require a mutation id');
const createRequest = { headers: { 'x-mutation-id': 'mut-1', 'idempotency-key': 'idem-1' }, body: {} };
const createContract = requireMutationContract(createRequest, OPERATION_KINDS.CREATE_IDEMPOTENT);
assert(createContract.expectedVersion === null, 'create operations do not require an entity version');
assert(expectCode(() => requireMutationContract(createRequest, OPERATION_KINDS.VERSIONED_MUTATION), 'expected_version_required'), 'existing-entity mutations require a version');
const updateRequest = { headers: { ...createRequest.headers, 'if-match': '3' }, body: {} };
assert(requireMutationContract(updateRequest, OPERATION_KINDS.VERSIONED_MUTATION).expectedVersion === 3, 'versioned mutation parses If-Match');
assert(expectCode(() => assertExpectedVersionMatches(4, 3), 'version_conflict_v2'), 'version conflict uses the canonical 412 contract');

const catalog = createCapabilityCatalog(['read', 'write']);
const projection = projectCapabilities(catalog, (capability) => capability === 'read');
assert(hasCapability(projection, 'read') && !hasCapability(projection, 'write'), 'generic capability engine projects explicit grants');
assert(!hasCapability(projection, 'unknown'), 'unknown capabilities deny safely');
assert(resolveHouseholdCapabilities('adult').invite_members === true, 'household permissions adopt the shared engine');
assert(resolveHouseholdCapabilities('guest').invite_members === false, 'household capability projection preserves denial');
assert(resolveCapabilities({ role: 'coordinator', membershipStatus: 'active' })['planner.view'] === true, 'Planner adapter preserves its catalog and matrix');

const legacy = legacyBodyToError({ error: 'not_found', message: 'Missing' }, 404);
assert(legacy.code === 'not_found' && legacy.message === 'Missing', 'legacy API errors normalize into canonical error data');
assert(legacyBodyToError({ error: { code: 'canonical' } }, 400).error.code === 'canonical', 'canonical envelopes pass through unchanged');

const contextRequest = { headers: { 'x-request-id': 'auth-request-1', 'x-mutation-id': 'auth-mutation-1' } };
const responseHeaders = {};
requestContextMiddleware(contextRequest, { set: (name, value) => { responseHeaders[name] = value; } }, () => {});
assert(contextRequest.requestId === 'auth-request-1' && responseHeaders['X-Request-Id'] === 'auth-request-1', 'request identity applies outside Planner routes');
assert(contextRequest.mutationId === 'auth-mutation-1' && responseHeaders['X-Mutation-Id'] === 'auth-mutation-1', 'valid mutation identity is uniformly exposed');

const coreBackend = [
  'backend/src/lib/capabilityEngine.js',
  'backend/src/lib/mutationContracts.js',
  'backend/src/lib/httpErrors.js',
  'backend/src/middleware/requestContextMiddleware.js',
  'backend/src/middleware/errorEnvelopeMiddleware.js',
];
assert(coreBackend.every((file) => !/require\([^)]*planner/i.test(read(file))), 'backend Core has no Planner dependency');
const coreFrontendDir = path.join(root, 'front/mi-front-limpio/services/core');
const coreFrontendSources = fs.readdirSync(coreFrontendDir).filter((name) => name.endsWith('.ts')).map((name) => fs.readFileSync(path.join(coreFrontendDir, name), 'utf8'));
assert(coreFrontendSources.every((source) => !/from\s+['"][^'"]*planner/i.test(source)), 'frontend Core has no Planner dependency');
assert(!/plannerCache/.test(read('front/mi-front-limpio/context/AuthContext.tsx')), 'AuthContext does not import Planner cache');
assert(!/plannerCache/.test(read('front/mi-front-limpio/context/HouseholdContext.tsx')), 'HouseholdContext does not import Planner cache');
assert(!/path\.startsWith\(['"]\/api\/planner/.test(read('front/mi-front-limpio/services/api.ts')), 'transport policy does not infer contracts from Planner URL prefixes');

const indexSource = read('backend/index.js');
const requestContextPosition = indexSource.indexOf('requestContextMiddleware');
const firstRoutePosition = indexSource.indexOf("app.use('/api/");
assert(requestContextPosition >= 0 && requestContextPosition < firstRoutePosition, 'request identity middleware is global and precedes routes');
assert(indexSource.indexOf('errorEnvelopeMiddleware') < firstRoutePosition, 'error envelope compatibility is global and precedes routes');
assert(requestContextPosition < indexSource.indexOf('express.json()'), 'request identity also precedes JSON parser failures');

const versionError = createHttpError(412, 'conflicto de version', 'version_conflict', { expected: 3 });
assert(versionError.statusCode === 412 && versionError.code === 'version_conflict' && versionError.details.expected === 3, 'createHttpError carries status, code and details');
assert(createHttpError(500, 'sin codigo', null).details === undefined, 'createHttpError omits details when absent');

const legacyRes = {
  statusCode: 0,
  payload: null,
  headers: {},
  set(name, value) { this.headers[name] = value; return this; },
  status(code) { this.statusCode = code; return this; },
  json(body) { this.payload = body; return this; },
};
sendError(legacyRes, versionError);
assert(legacyRes.statusCode === 412 && legacyRes.payload.error === 'conflicto de version' && legacyRes.payload.code === 'version_conflict', 'sendError emits the legacy error body');
sendError(legacyRes, new Error('fallo sin codigo'));
assert(legacyRes.statusCode === 500 && !legacyRes.payload.code, 'sendError falls back to 500 when the code is missing');

const clientEnvelope = buildApiErrorEnvelope(versionError, { requestId: 'req-core-1' });
assert(clientEnvelope.statusCode === 412 && clientEnvelope.envelope.error.request_id === 'req-core-1' && clientEnvelope.envelope.error.details.expected === 3, 'client error envelope keeps sanitized details and request id');
const serverError = new Error('secreto interno de base de datos');
serverError.code = 'db_failure';
serverError.details = { sql: 'NO_DEBE_FILTRARSE' };
const serverEnvelope = buildApiErrorEnvelope(serverError, { requestId: 'req-core-2' });
assert(serverEnvelope.envelope.error.message === 'Error interno.' && serverEnvelope.envelope.error.details === undefined, 'server error envelope never leaks raw details');

sendApiError(legacyRes, versionError, { requestId: 'req-core-3' });
assert(legacyRes.statusCode === 412 && legacyRes.payload.error.code === 'version_conflict' && legacyRes.payload.error.request_id === 'req-core-3', 'sendApiError writes the canonical envelope');

const middlewareRes = { statusCode: 200, payload: null, json(body) { this.payload = body; return this; } };
errorEnvelopeMiddleware({ requestId: 'req-core-mw' }, middlewareRes, () => {});
middlewareRes.statusCode = 404;
middlewareRes.json({ error: 'not_found' });
assert(middlewareRes.payload.error.request_id === 'req-core-mw' && middlewareRes.payload.error.code === 'not_found', 'error envelope middleware normalizes legacy 404 bodies');
middlewareRes.statusCode = 202;
middlewareRes.json({ ok: true });
assert(middlewareRes.payload.ok === true, 'error envelope middleware passes successful bodies unchanged');

const msgOnlyError = createHttpError(400, undefined, 'bad_request');
msgOnlyError.message = undefined;
sendError(legacyRes, msgOnlyError, 'mensaje por defecto');
assert(legacyRes.payload.error === 'mensaje por defecto', 'sendError uses the fallback message when the error has none');
const anonymousEnvelope = buildApiErrorEnvelope(undefined, undefined);
assert(anonymousEnvelope.statusCode === 500 && anonymousEnvelope.envelope.error.code === 'internal_error' && anonymousEnvelope.envelope.error.request_id === null, 'error envelope degrades safely without an error or request');
const clientDetailsEnvelope = buildApiErrorEnvelope(createHttpError(400, 'sin detalles'), undefined);
assert(clientDetailsEnvelope.envelope.error.details === undefined, 'client error envelope omits absent details');
const explicitCodeError = legacyBodyToError({ error: 'texto libre', code: 'dominio_error', details: { campo: 'x' } }, 400);
assert(explicitCodeError.code === 'dominio_error' && explicitCodeError.details.campo === 'x', 'legacy body error honors an explicit code and details');
const serverLegacyError = legacyBodyToError({ error: 'fallo del servidor', details: { nocturno: true } }, 500);
assert(serverLegacyError.code === 'request_failed' && serverLegacyError.details === undefined, 'legacy body error drops details on server failures');
const canonicalBody = { error: { code: 'ya_canonical', message: 'Mensaje', request_id: 'req-legacy' } };
middlewareRes.statusCode = 422;
middlewareRes.json(canonicalBody);
assert(middlewareRes.payload.error.request_id === 'req-legacy', 'error envelope middleware preserves an existing canonical request id');
const legacyPlainError = new Error('fallo 503');
legacyPlainError.statusCode = 503;
const serverEnvelopeViaSend = (() => { sendApiError(legacyRes, serverError, { requestId: 'req-core-5xx' }); return legacyRes; })();
assert(serverEnvelopeViaSend.statusCode === 500 && serverEnvelopeViaSend.headers['X-Request-Id'] === 'req-core-5xx', 'sendApiError sanitizes 5xx and still sets the request id');
assert(legacyBodyToError({ error: 'sin codigo conocido' }, 400).code === 'request_failed', 'legacy body error defaults to request_failed');

assert(isFinalRole(FINAL_ROLES[0]) && !isFinalRole('role_inexistente'), 'final role checks accept canonical roles and deny unknown ones');
assert(isFunctionalMembershipStatus('active') && !isFunctionalMembershipStatus('inexistente'), 'membership status checks distinguish functional states');
assert(isAllMembershipStatus('suspended') && !isAllMembershipStatus('inexistente'), 'membership status checks cover all states');
assert(Object.keys(getDefaultHouseholdPermissions()).length > 0, 'default household permissions are exposed as a snapshot');
const overrideConfig = { permissions: { invite_members: { adult: false }, approve_members: { adult: true }, remove_members: { adult: true }, manage_roles: { adult: true }, assign_coordinator: { adult: true }, edit_config: { adult: true } } };
assert(canInviteMembers('adult') === true && canInviteMembers('adult', overrideConfig) === false, 'household invites honor explicit role overrides');
assert(canInviteMembers('role_inexistente') === false, 'household invites deny unknown roles');
assert(canApproveMembers('adult', overrideConfig) === true && canApproveMembers('role_inexistente') === false, 'household approvals honor overrides and deny unknown roles');
assert(canRemoveMember('adult', 'coordinator') === false && canRemoveMember('adult', 'guest', overrideConfig) === true && canRemoveMember('role_inexistente', 'guest') === false, 'household member removal protects coordinators and unknown actors');
assert(canManageRoles('adult', overrideConfig) === true && canManageRoles('role_inexistente') === false, 'household role management honors overrides and denies unknown actors');
assert(canAssignCoordinator('adult', overrideConfig) === true && canAssignCoordinator('role_inexistente') === false, 'household coordinator assignment honors overrides and denies unknown actors');
assert(canEditConfig('adult', overrideConfig) === true && canEditConfig('role_inexistente') === false, 'household config editing honors overrides and denies unknown actors');

console.log(`\nHOMEPLUS CORE CONTRACTS: ${passed} assertions passed.`);
