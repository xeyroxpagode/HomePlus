// Generador de entregables estructurados (SOLO LECTURA del producto; escribe SOLO en closure-discovery/).
// Sale de: 03_TOOL_CATALOG.json (176 operaciones / 92 tools) + _discovery_data.cjs.
const fs = require('fs');
const path = require('path');
const { discovered } = require('./_discovery_data.cjs');

const DIR = __dirname;
const PREV = path.join(DIR, '..', '03_TOOL_CATALOG.json');
const prev = JSON.parse(fs.readFileSync(PREV, 'utf8'));
const prevOps = [];
for (const d of prev.domains) for (const o of d.operations) prevOps.push({ ...o, domain: d.domain });
const prevTools = new Map(prev.tools.map(t => [t.tool_id, t]));

// ---------------------------------------------------------------------------
// Politica de reclamacion de las 176 operaciones anteriores (Etapa D).
// Regla Actor A: maximizar cobertura; la dificultad o "no aporta al recorrido"
// NO justifica DEFERRED. Solo seguridad, autoridad, dependencia real o no-producto.
// ---------------------------------------------------------------------------
const RECLASS = {
  // EXCLUDED por seguridad / no-producto: se mantienen (razon demostrable).
  'identity.register': ['EXCLUDED_SECURITY', 'Credenciales/sesion: nunca herramienta del LLM.'],
  'identity.login': ['EXCLUDED_SECURITY', 'Credenciales/sesion: el inicio de sesion pertenece a la app, nunca al modelo.'],
  'identity.refresh': ['EXCLUDED_SECURITY', 'Renovacion de token: credenciales de sesion, fuera de la autoridad del LLM.'],
  'identity.logout': ['EXCLUDED_SECURITY', 'Cierre de sesion: credenciales de sesion, gestion exclusivo de la app.'],
  'identity.user-metadata.update': ['EXCLUDED_SECURITY', 'Escribe auth.users.user_metadata via service-role (ADG-9).'],
  'notifications.preferences.update': ['EXCLUDED_SECURITY', 'Requiere service-role; sin bandeja real.'],
  'notifications.devices.register': ['EXCLUDED_SECURITY', 'Registro de dispositivo nativo, no del asistente.'],
  'feed.posts.list': ['EXCLUDED_NOT_PRODUCT', 'MOCK_POSTS en memoria; no existe backend.'],
  'feed.posts.create': ['EXCLUDED_NOT_PRODUCT', 'useState local; no existe backend.'],
  'households.join': ['EXCLUDED_NOT_PRODUCT', 'Flujo de onboarding de la app, no del asistente.'],
  'identity.profile.update': ['TARGET_IMPLEMENT', 'Reclasificado: escritura de perfil segura sin service-role (ver descubrimiento).'],
  'identity.avatar.update': ['BLOCKED_DEPENDENCY', 'Multipart + compresion de imagen; requiere UI nativa (PD-05).'],

  // BLOCKED: razon real, con responsable y condicion de desbloqueo.
  'households.create': ['BLOCKED_UNSAFE', 'Cambia el workspace raiz durante la conversacion; alternativa UI dedicada (PD-04).'],
  'households.set-active': ['BLOCKED_UNSAFE', 'Cambia el hogar activo e invalida el contexto de la propuesta (PD-04).'],
  'households.finalize-member': ['BLOCKED_UNSAFE', 'Expulsion de persona: accion administrativa destructiva (PD-04).'],
  'planner.plans.structure': ['BLOCKED_UNSAFE', 'Changeset estructural completo: no seguro desde lenguaje natural.'],
  'planner.plans.unarchive': ['BLOCKED_AUTHORITY', 'Capability goal.archive=false para los 6 roles por defecto (MIG/20260722040000:355).'],
  'planner.presets.publish': ['BLOCKED_AUTHORITY', 'Publicacion global de preset: no apta para agente; requiere UI editorial.'],
  'finance.transfers.create': ['BLOCKED_DEPENDENCY', 'R1-b: hash de idempotencia con scopeType fijo PERSONAL; colision entre contextos no descartada.'],
  'finance.balance.correction': ['PRODUCT_DECISION', 'Correccion de saldo: decision financiera humana; sin compensatorios ficticios (PD-03).'],
  'finance.payments.dues.register': ['PRODUCT_DECISION', 'R1-d: crea transaccion real, scope no reforzado en despacho (PD-03).'],
  'inventory.purchases.finalize': ['PRODUCT_DECISION', 'Requiere register_in_finance y decision de gasto explicita (PD-01).'],
  'homecloud.content.access': ['BLOCKED_DEPENDENCY', 'URL firmada a bytes: requiere SEE/HOMI-B real; no inventar contenido.'],
  'homecloud.content.analyze': ['BLOCKED_DEPENDENCY', 'HOMI-B no garantizado; sin procesamiento visual no se devuelve resultado.'],
  'messages.attachments.download': ['BLOCKED_DEPENDENCY', 'URL firmada a bytes 300s; requiere SEE/HOMI-B.'],
  'presence.locations.list': ['BLOCKED_AUTHORITY', 'Geolocalizacion de terceros: consentimiento vigente no verificable por el LLM (PD-02).'],
  'presence.my-location.update': ['BLOCKED_AUTHORITY', 'Seguimiento de ubicacion: requiere decision funcional explicita (PD-02).'],
  'planner.tasks.verify': ['BLOCKED_AUTHORITY', 'Prohibida auto-verificacion; exige otro actor.'],
  'planner.tasks.evidence': ['BLOCKED_DEPENDENCY', 'Requiere foto/comentario; depende de SEE/adjuntos reales.'],

  // DEFERRED -> TARGET_IMPLEMENT salvo razon demostrable (politica Actor A).
  'households.invite-link.create': ['TARGET_IMPLEMENT', 'Coordinator; confirmacion obligatoria.'],
  'households.invite-link.revoke': ['TARGET_IMPLEMENT', 'Revocar acceso: confirmacion reforzada, coordinator.'],
  'households.join-request.approve': ['TARGET_IMPLEMENT', 'Coordinator; decision de ingreso confirmada.'],
  'households.join-request.reject': ['TARGET_IMPLEMENT', 'Coordinator; confirmacion.'],
  'households.member.role.update': ['PRODUCT_DECISION', 'Cambio de privilegios: exponer a coordinator via HOMI o solo UI (PD-04).'],
  'households.role-request.create': ['TARGET_IMPLEMENT', 'Solicitud auto-servicio del actor.'],
  'households.role-request.approve': ['PRODUCT_DECISION', 'Aprobacion de privilegios (PD-04).'],
  'households.role-request.reject': ['PRODUCT_DECISION', 'Rechazo de privilegios (PD-04).'],
  'households.role-request.cancel': ['TARGET_IMPLEMENT', 'Solo solicitante; cancelacion de su propia solicitud.'],
  'planner.tasks.reactivate': ['TARGET_IMPLEMENT', 'Transicion de ciclo con confirmacion.'],
  'planner.events.trash': ['TARGET_IMPLEMENT', 'Papelera con confirmacion.'],
  'planner.events.restore': ['TARGET_IMPLEMENT', 'Restauracion.'],
  'planner.goals.close': ['TARGET_IMPLEMENT', 'Requiere closed_reason; herramienta tipada.'],
  'planner.goals.fail': ['TARGET_IMPLEMENT', 'Cambio de estado confirmado.'],
  'planner.goals.reopen': ['TARGET_IMPLEMENT', 'Ciclo de meta.'],
  'planner.plans.create': ['TARGET_IMPLEMENT', 'Payload estructurado; tool tipada por seccion, no JSON libre.'],
  'planner.plans.update': ['TARGET_IMPLEMENT', 'Tool tipada por seccion.'],
  'planner.plans.transition': ['TARGET_IMPLEMENT', 'Transicion con capability por accion.'],
  'planner.responsibilities.create': ['TARGET_IMPLEMENT', 'Genera tareas derivadas via materializeHousehold.'],
  'planner.responsibilities.lifecycle': ['TARGET_IMPLEMENT', 'Seis transiciones: descomponer en tools tipadas por accion.'],
  'planner.schedules.create': ['TARGET_IMPLEMENT', 'Exige pertenencia del actor.'],
  'planner.schedules.update': ['TARGET_IMPLEMENT', 'Anadir Idempotency-Key/expected_version en el binding.'],
  'planner.schedules.delete': ['TARGET_IMPLEMENT', 'Confirmacion; anadir idempotencia.'],
  'planner.presets.create': ['TARGET_IMPLEMENT', 'Tool tipada por plantilla.'],
  'planner.drafts.autosave': ['EXCLUDED_NOT_PRODUCT', 'Autoguardado lo hace la app; el asistente no debe generar borradores implicitos (razon funcional, no pereza).'],
  'planner.drafts.discard': ['TARGET_IMPLEMENT', 'Descartar borrador; rutas trash/restore son 410.'],
  'planner.tasks.audit.get': ['TARGET_IMPLEMENT', 'Anadir exigencia planner.audit.view en servidor (P1).'],
  'finance.accounts.create': ['TARGET_IMPLEMENT', 'Alta de cuenta; confirmacion reforzada.'],
  'finance.accounts.update': ['TARGET_IMPLEMENT', 'Solo nombre/cierre/vencimiento.'],
  'finance.accounts.archive': ['TARGET_IMPLEMENT', 'Ciclo de cuenta.'],
  'finance.accounts.anchor': ['TARGET_IMPLEMENT', 'Alto impacto contable; confirmacion reforzada.'],
  'finance.transactions.correct': ['TARGET_IMPLEMENT', 'Requiere expectedVersion; tool tipada.'],
  'finance.transactions.trash': ['TARGET_IMPLEMENT', 'Bloqueos por comision/pagos: validar.'],
  'finance.transactions.restore': ['TARGET_IMPLEMENT', 'Estado incompatible: validar.'],
  'finance.refunds.create': ['TARGET_IMPLEMENT', 'Hereda cuenta/moneda/categoria; confirmacion.'],
  'finance.refunds.correct': ['TARGET_IMPLEMENT', 'Correccion de devolucion; confirmacion.'],
  'finance.installments.purchase': ['TARGET_IMPLEMENT', '2..60 cuotas; confirmacion reforzada (compromiso futuro).'],
  'finance.pools.allocate': ['TARGET_IMPLEMENT', 'Movimiento de reserva; confirmacion.'],
  'finance.pools.release': ['TARGET_IMPLEMENT', 'Movimiento de reserva; confirmacion.'],
  'finance.pools.transfer': ['TARGET_IMPLEMENT', 'Movimiento de reserva; confirmacion.'],
  'finance.spending-limits.create': ['TARGET_IMPLEMENT', 'Configuracion de limite; confirmacion.'],
  'inventory.purchases.cancel': ['TARGET_IMPLEMENT', 'Transicion de sesion.'],
  'inventory.products.trash': ['TARGET_IMPLEMENT', 'Papelera con version.'],
  'inventory.locations.create': ['TARGET_IMPLEMENT', 'Alta de ubicacion.'],
  'inventory.restock.approve': ['TARGET_IMPLEMENT', 'Solo coordinator/adult; agrega a lista.'],
  'assets.create': ['TARGET_IMPLEMENT', 'Requiere profile estructural; tool tipada por perfil.'],
  'assets.archive': ['TARGET_IMPLEMENT', 'Episodios append-only; confirmacion.'],
  'assets.trash': ['TARGET_IMPLEMENT', 'Papelera con Idempotency-Key.'],
  'assets.restore': ['TARGET_IMPLEMENT', 'Restaura estado exacto.'],
  'assets.record.link': ['TARGET_IMPLEMENT', 'N:M; quitar no elimina archivo.'],
  'homecloud.favorite': ['TARGET_IMPLEMENT', 'Preferencia por account_id.'],
  'homecloud.album.create': ['TARGET_IMPLEMENT', 'Album no es dueno de archivos (AGENTS #46).'],
  'homecloud.content.register': ['BLOCKED_DEPENDENCY', 'Carga de archivos: requiere UI de seleccion real (PD-05).'],
  'messages.messages.react': ['TARGET_IMPLEMENT', 'Reacciones; confirmacion no requerida (R1).'],
  'messages.conversations.read': ['TARGET_IMPLEMENT', 'Efecto de lectura; R1.'],
};

const DEST_LABEL = {
  TARGET_IMPLEMENT: 'OBJETIVO: tool con contrato estructurado en el catalogo final',
  BLOCKED_DEPENDENCY: 'BLOQUEADO por dependencia tecnica/proveedor real',
  BLOCKED_AUTHORITY: 'BLOQUEADO por autoridad/consentimiento no verificable',
  BLOCKED_UNSAFE: 'BLOQUEADO por inseguridad demostrable desde lenguaje natural',
  EXCLUDED_SECURITY: 'EXCLUIDO permanentemente por seguridad',
  EXCLUDED_NOT_PRODUCT: 'EXCLUIDO: no es funcionalidad de producto o es infraestructura',
  PRODUCT_DECISION: 'PENDIENTE DE DECISION DE ACTOR A (default seguro: no exponer)',
};

// ---------------------------------------------------------------------------
// 1) INVENTARIO COMPLETO (176 anteriores reconciliados + descubrimientos)
// ---------------------------------------------------------------------------
const inventory = [];
const seen = new Set();
const overlapIds = [];
for (const o of prevOps) {
  const dec = RECLASS[o.operation_id];
  const final = dec ? dec[0] : (o.destination === 'IMPLEMENT' ? 'TARGET_IMPLEMENT' : `LEGACY_${o.destination}`);
  const reason = dec ? dec[1] : o.evidence_reason;
  seen.add(o.operation_id);
  inventory.push({
    operation_id: o.operation_id,
    source: 'catalog_176',
    domain: o.domain,
    previous_destination: o.destination,
    final_destination: final,
    final_destination_label: DEST_LABEL[final] || 'Sin cambio (heredado)',
    reclassification_reason: reason,
    risk_class_before: o.risk_class,
    http: o.http,
    canonical_service: o.canonical_service,
    required_capabilities: o.required_capabilities || [],
    household_scope: o.household_scope,
    evidence: [{ type: 'catalog', ref: '03_TOOL_CATALOG.json', detail: o.evidence_reason || '' }],
    tool_contract_ref: final === 'TARGET_IMPLEMENT' ? o.operation_id : null,
  });
}
for (const d of discovered) {
  if (seen.has(d.id)) {
    overlapIds.push(d.id);
    const item = inventory.find(x => x.operation_id === d.id);
    item.final_destination = d.destination;
    item.final_destination_label = DEST_LABEL[d.destination];
    item.reclassification_reason = d.reason || item.reclassification_reason;
    item.evidence.push({ type: 'independent_discovery', ref: d.evidence, detail: d.service });
    item.http = { method: d.method, path: d.path };
    item.canonical_service = d.service;
    continue;
  }
  seen.add(d.id);
  inventory.push({
    operation_id: d.id,
    source: 'independent_discovery',
    domain: d.domain,
    entity: d.entity,
    operation: d.action,
    previous_destination: null,
    final_destination: d.destination,
    final_destination_label: DEST_LABEL[d.destination],
    reclassification_reason: d.reason || 'Capacidad real confirmada en codigo; se incorpora al alcance segun politica de maxima cobertura.',
    risk_class_before: d.risk,
    http: { method: d.method, path: d.path },
    canonical_service: d.service,
    required_capabilities: [],
    household_scope: 'HOUSEHOLD',
    evidence: [{ type: 'independent_discovery', ref: d.evidence, detail: d.service }],
    tool_contract_ref: d.destination === 'TARGET_IMPLEMENT' ? d.id : null,
  });
}

const byFinal = inventory.reduce((m, x) => { m[x.final_destination] = (m[x.final_destination] || 0) + 1; return m; }, {});
const byDomain = {};
for (const x of inventory) { byDomain[x.domain] ||= {}; byDomain[x.domain][x.final_destination] = (byDomain[x.domain][x.final_destination] || 0) + 1; }

const inventoryDoc = {
  schema_version: '1.0.0',
  generated_at: new Date().toISOString(),
  pass: '1/2 discovery & contract freeze',
  sources: {
    previous_catalog: 'docs/homi/full-integration/03_TOOL_CATALOG.json',
    previous_operations: prevOps.length,
    previous_tools: prev.tools.length,
    independent_audits: [
      'backend/index.js + backend/src/routes/*.js (365 declaraciones / 380 efectivas)',
      'backend/src/services/** + backend/src/lib/** (exports)',
      'supabase/migrations/*.sql (146 archivos)',
      'front/mi-front-limpio/services/** + screens/**',
    ],
    newly_discovered: discovered.length,
  },
  policy: 'Maximizacion de cobertura funcional (Actor A). DEFERRED solo con razon funcional/seguridad demostrable; la complejidad no excluye.',
  totals: {
    operations_total: inventory.length,
    previous: prevOps.length,
    newly_discovered: discovered.length,
    duplicate_ids_collapsed: overlapIds.length,
    duplicate_ids: overlapIds,
    by_final_destination: byFinal,
    by_domain: byDomain,
  },
  operations: inventory,
};
fs.writeFileSync(path.join(DIR, '02_COMPLETE_FUNCTIONAL_INVENTORY.json'), JSON.stringify(inventoryDoc, null, 2) + '\n');

// ---------------------------------------------------------------------------
// 2) CATALOGO FINAL DE TOOLS (contratos estructurados para cada TARGET_IMPLEMENT)
// ---------------------------------------------------------------------------
// Normalización del canonical_service a formato `.js::symbol` consumible por el
// contrato de v1-catalog.test.js (`/\.js::[A-Za-z_$][\w$]*$/`).
function normalizeService(service) {
  if (!service) return null;
  if (/\.js::[A-Za-z_$][\w$]*$/.test(service)) return service;
  const i = service.lastIndexOf('::');
  if (i > 0) {
    const left = service.slice(0, i);
    return `${left.endsWith('.js') ? left : `${left}.js`}::${service.slice(i + 2)}`;
  }
  const m = service.match(/^(.*)\.([A-Za-z_$][\w$]*)$/);
  if (m) {
    const left = m[1];
    return `${left.endsWith('.js') ? left : `${left}.js`}::${m[2]}`;
  }
  return `${service}.js`;
}

const CAPS = {
  identity: [], households: [], home: ['planner.view'], planner: ['planner.view'],
  finance: [], inventory: ['inventory.view'], assets: ['assets.view'],
  homecloud: ['homecloud.view'], messages: [], hplus: [], settings: [],
};
const SCOPE = { identity: 'PERSONAL_HOUSEHOLD', finance: 'PERSONAL_HOUSEHOLD', households: 'HOUSEHOLD', settings: 'PERSONAL' };

const COMMON_RULES = [
  'additionalProperties=false; se rechazan campos desconocidos.',
  'El modelo NO puede enviar actor_id, household_id, membership_id, role, authorization, tool_call_id, catalog_digest, request_id ni trace_id.',
  'Identidad y hogar derivados del bearer en el servidor (getPlannerContext / resolveFinanceContext / getHouseholdRequestContext).',
  'Moneda ISO 4217 /^[A-Z]{3}$/ e importe decimal textual de hasta 4 decimales cuando aplica.',
];
const ERROR_MAP = { '400':'invalid_arguments','401':'not_authenticated','403':'forbidden_capability','404':'not_found_or_not_authorized','409':'conflict','412':'version_conflict','413':'payload_too_large','415':'unsupported_media_type','422':'validation_error','5xx':'provider_error_retryable' };

function propsFor(x) {
  const p = {
    limit: { type:'integer', minimum:1, maximum:100 },
    query: { type:'string', minLength:1, maxLength:200 },
    period: { type:'string', pattern:'^[0-9]{4}-(0[1-9]|1[0-2])$' },
    context: { type:'string', enum:['PERSONAL','HOUSEHOLD'] },
  };
  const id = x.operation_id || x.id;
  const isGet = /\.get$|\.list$|\.history$|\.summary$|\.get_.+$/.test(id);
  if (!isGet) {
    p.expected_version = { type:'string', minLength:1, maxLength:64 };
    p.entity_ref = { type:'string', minLength:1, maxLength:64 };
  }
  if (x.domain === 'finance') {
    p.amount = { type:'string', pattern:'^-?(0|[1-9][0-9]*)(\\.[0-9]{1,4})?$' };
    p.currency = { type:'string', pattern:'^[A-Z]{3}$' };
    p.date = { type:'string', pattern:'^[0-9]{4}-[0-9]{2}-[0-9]{2}$' };
    p.account_ref = { type:'string', minLength:1, maxLength:64 };
  }
  if (x.domain === 'planner') {
    p.task_ref = { type:'string', minLength:1, maxLength:64 };
    p.title = { type:'string', minLength:1, maxLength:200 };
    p[x.operation_id === 'planner.tasks.create' || x.operation_id === 'planner.tasks.update' ? 'dueDate' : 'date'] = { type:'string', pattern:'^[0-9]{4}-[0-9]{2}-[0-9]{2}$' };
    p.dueTime = { type:'string', pattern:'^([01][0-9]|2[0-3]):[0-5][0-9]$' };
    p.checklist = { type:'array', items:{ type:'object', additionalProperties:false, properties:{ text:{type:'string'}, checked:{type:'boolean'} }, required:['text'] } };
  }
  if (x.domain === 'messages') {
    p.conversation_ref = { type:'string', minLength:1, maxLength:64 };
    p.body = { type:'string', minLength:1, maxLength:4000 };
  }
  if (x.domain === 'inventory') {
    p.product_ref = { type:'string', minLength:1, maxLength:64 };
    p.delta = { type:'integer' };
  }
  if (x.domain === 'homecloud') {
    p.content_ref = { type:'string', minLength:1, maxLength:64 };
    p.album_ref = { type:'string', minLength:1, maxLength:64 };
  }
  if (x.domain === 'assets') {
    p.asset_ref = { type:'string', minLength:1, maxLength:64 };
  }
  return p;
}

function buildContract(x) {
  const id = x.operation_id || x.id;
  const domain = x.domain || 'home';
  const risk = (x.risk_class_before || '').includes('WRITE') ? x.risk_class_before
    : (x.risk_before || x.risk || (x.risk_class_before === 'CONFIRM' ? 'R2_CONFIRMED_WRITE' : null));
  const read = /^R0_READ$/.test(risk) || String(x.risk_class_before).includes('READ') || /\.get$|\.list$|\.summary$|\.history$|\.discovery$|\.search$|\.progress$|\.privacy\.get$|\.audit\.get$/.test(id);
  // Política NO uniforme: reforzada solo para efecto financiero, destructivo,
  // privilegios o cambio de estado de negocio. Reversible => preview + confirm.
  const R2_PATTERN = /\.complete$|\.trash$|\.delete$|\.permanent|\.cancel$|\.reject$|\.approve$|\.archive$|\.settle$|\.correct$|\.refund|\.anchor$|\.balance|\.transfer|\.role|\.finalize$|\.publish$|\.remove$|\.unlink$|\.empty$|\.clear$|\.distribute$|\.assign$|\.unassign$|\.profile$|\.unarchive$|messages\.messages\.send|finance\.expenses\.create|finance\.incomes\.create|finance\.pools\.create|inventory\.purchases\.finance|homecloud\.memories\.trash/;
  const riskClass = read ? 'R0_READ'
    : (domain === 'finance' || domain === 'messages' || R2_PATTERN.test(id) || /R2_CONFIRMED_WRITE/.test(String(x.risk_class_before)) && !/\.react$|\.read$|\.favorite$|\.cover$|\.membership$/.test(id)
        ? 'R2_CONFIRMED_WRITE' : 'R1_SAFE_WRITE');
  const confirmation = riskClass === 'R0_READ' ? 'NONE'
    : riskClass === 'R2_CONFIRMED_WRITE' ? 'CONFIRM_REINFORCED' : 'PREVIEW_THEN_CONFIRM';
  const existing = prevTools.get(id);
  const http = x.http || {};
  const desc = `${domain} · ${x.operation || (x.operation_id || '').split('.').slice(-1)[0]}. ${x.reclassification_reason || x.evidence_reason || ''}`.slice(0, 400);
  return {
    tool_id: id,
    domain,
    entity: x.entity || id.split('.').slice(-2,-1)[0] || domain,
    operation: x.operation || id.split('.').slice(-1)[0],
    name: id.split('.').slice(-1)[0],
    description: desc,
    intent_examples: existing?.intent_examples || [
      `«${(x.operation || id.split('.').slice(-1)[0]).replace(/_/g,' ')} en ${domain}»`,
    ],
    risk_class: riskClass,
    read_write: read ? 'READ' : 'WRITE',
    confirmation_policy: confirmation,
    required_capabilities: existing?.required_capabilities || CAPS[domain] || [],
    household_scope: existing?.household_scope || SCOPE[domain] || 'HOUSEHOLD',
    version: '1.0.0',
    source: x.source || (existing ? 'catalog_176' : 'independent_discovery'),
    previous_destination: x.previous_destination || (existing ? 'IMPLEMENT' : null),
    canonical_service: normalizeService(x.canonical_service || existing?.canonical_service || null),
    http: { method: http.method || 'GET', path: http.path || '' },
    input_schema: {
      type: 'object',
      additionalProperties: false,
      properties: propsFor(x),
      required: [],
    },
    output_schema: {
      type: 'object', additionalProperties: true,
      properties: {
        data: { type: 'object' },
        meta: { type: 'object', properties: { truncated: { type:'boolean' }, omitted_count: { type:'integer' }, resource_resolution: { type:'object' } } },
      },
    },
    validation_rules: COMMON_RULES,
    resource_resolution: 'Referencias opacas resueltas por busqueda acotada al household autorizado; 0 => NOT_FOUND, >1 => AMBIGUOUS con candidatos compactos; nunca eleccion arbitraria.',
    ambiguity_policy: 'Devolver candidatos compactos y pedir desambiguacion antes de cualquier escritura.',
    authority: {
      actor: 'derivado_del_bearer',
      household: 'derivado_del_token',
      scope: SCOPE[domain] || 'HOUSEHOLD',
      revalidate_server_side: true,
      forbidden_model_fields: ['actor_id','household_id','membership_id','role','authorization','tool_call_id','catalog_digest','request_id','trace_id'],
    },
    execution: {
      handler: existing?.execution_handler || `homiRuntime/handlers/${domain}.${x.operation || id.split('.').slice(-1)[0]}`,
      canonical_service: normalizeService(x.canonical_service || existing?.canonical_service || null),
      http: { method: http.method || 'GET', path: http.path || '' },
      transaction: read ? null : 'apollo: servizio canonico posee transaccion/RPC atomica; HOMI no abre transacciones propias',
      idempotency: read ? 'N/A' : 'X-Mutation-Id + Idempotency-Key derivados de proposal_id + hash de argumentos normalizados',
      concurrency: read ? 'N/A' : 'If-Match/expected_version -> 412 version_conflict; una sola propuesta activa por entidad',
      ledger: read ? 'homi.tool.execution.read' : 'homi.tool.execution.started + homi.tool.execution.write',
      retries: read ? 'solo 5xx con backoff acotado' : 'sin reintentos automaticos; outcome incierto se verifica contra servicio canonico',
      compensation_policy: read
        ? null
        : 'No se fabrican compensaciones; si el estado es incierto se registra outcome_uncertain y se verifica contra el servicio autoritativo; nunca se reintenta un write ya despachado.',
    },
    side_effects: read ? [] : ['mutacion canonica en BD de producto', 'audit_events/outbox_events', 'homi.execution_steps'],
    error_mapping: ERROR_MAP,
    test_cases: read
      ? ['happy_path','invalid_input','capability_denied','other_household','session_expired','empty_result','truncation_metadata','no_side_effects']
      : ['happy_path','invalid_input','preview_shows_exact_args','capability_denied','other_household','session_expired','confirmation_binding','stale_confirmation_rejected','duplicate_submission_idempotent','version_conflict_412','provider_error_no_double_write','persistence_verified','ledger_written','compensation_not_fabricated'],
    evidence: x.evidence || [{ type: 'catalog', ref: '03_TOOL_CATALOG.json' }],
  };
}

const targetOps = inventory.filter(x => x.final_destination === 'TARGET_IMPLEMENT');
const tools = targetOps.map(buildContract);
const toolIds = tools.map(t => t.tool_id);
const dupTools = toolIds.filter((v,i,a) => a.indexOf(v) !== i);
const readCount = tools.filter(t => t.read_write === 'READ').length;
const writeCount = tools.filter(t => t.read_write === 'WRITE').length;

const catalogDoc = {
  schema_version: '2.0.0',
  generated_at: new Date().toISOString(),
  pass: '1/2 discovery & contract freeze',
  target: { repo:'https://github.com/xeyroxpagode/HomePlus.git', branch:'homplus-18-11', commit:'d8edd49236457ffe1ac66bb9e836ef4117ac980d', worktree_branch:'homi/full-integration-18-11' },
  policy: 'Catalogo final con contrato estructurado por tool. El contrato es la autoridad; el runtime debe regenerarse desde el. Sin ejecutor generico de JSON arbitrario.',
  summary: {
    previous_tools: prev.tools.length,
    target_tools: tools.length,
    read_tools: readCount,
    write_tools: writeCount,
    duplicate_tool_ids: dupTools,
    by_domain: tools.reduce((m,t)=>{m[t.domain]=(m[t.domain]||0)+1;return m;},{}),
    by_confirmation: tools.reduce((m,t)=>{m[t.confirmation_policy]=(m[t.confirmation_policy]||0)+1;return m;},{}),
  },
  tools,
};
fs.writeFileSync(path.join(DIR, '04_TOOL_CATALOG_FINAL.json'), JSON.stringify(catalogDoc, null, 2) + '\n');

console.log(JSON.stringify({
  inventory_total: inventory.length,
  previous: prevOps.length,
  discovered: discovered.length,
  by_final_destination: byFinal,
  target_tools: tools.length,
  read_tools: readCount,
  write_tools: writeCount,
  duplicate_tool_ids: dupTools,
}, null, 2));
