const fs = require('fs');
const BASE = 'http://127.0.0.1:3100';
// Token de la cuenta QA aislada. Se suministra por entorno; la ruta local es
// sólo un helper de la sesión y no forma parte del contrato del proyecto.
const TOKEN_PATH = process.env.HOMI_QA_TOKEN_FILE
  || 'C:\\Users\\thega\\AppData\\Local\\Temp\\opencode\\homi_qa_token.txt';
if (!process.env.HOMI_QA_TOKEN && !fs.existsSync(TOKEN_PATH)) {
  console.error('Falta HOMI_QA_TOKEN o el archivo HOMI_QA_TOKEN_FILE (cuenta QA aislada).');
  process.exit(2);
}
const TOKEN = process.env.HOMI_QA_TOKEN || fs.readFileSync(TOKEN_PATH, 'utf8').trim();

async function call(path, method, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let payload; try { payload = text ? JSON.parse(text) : {}; } catch { payload = { raw: text.slice(0, 300) }; }
  return { status: res.status, payload };
}

const results = [];
function check(name, ok, detail) { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' :: ' + detail : ''}`); }

(async () => {
  // 0. sin bearer = 401
  const anon = await fetch(BASE + '/api/homi/v1/tools');
  check('sin_bearer_401', anon.status === 401, 'status=' + anon.status);

  // 1. discovery
  const discovery = await call('/api/homi/v1/tools', 'GET');
  const toolIds = discovery.payload?.tools?.map((t) => t.tool_id) || [];
  check('discovery_200', discovery.status === 200, 'tools=' + toolIds.length);
  check('discovery_projection_only_3_keys',
    discovery.status === 200 && discovery.payload.tools.every((t) => Object.keys(t).sort().join(',') === 'description,input_schema,tool_id'),
    'keys=' + (discovery.payload.tools[0] && Object.keys(discovery.payload.tools[0]).join(',')));
  check('discovery_includes_home_summary', toolIds.includes('home.summary.get'));
  check('discovery_excludes_feed', !toolIds.some((id) => id.startsWith('feed.')));

  // 2. claims del cliente no aceptadas como autoridad
  const forged = await call('/api/homi/v1/tools/planner.tasks.list/invoke', 'POST', {
    actor_id: '00000000-0000-0000-0000-000000000000',
    household_id: '00000000-0000-0000-0000-000000000000',
  });
  check('claims_forjadas_rechazadas', forged.status !== 200, 'status=' + forged.status);

  // 3. tools READ reales
  for (const [toolId, args] of [
    ['home.summary.get', {}],
    ['planner.tasks.list', {}],
    ['finance.accounts.list', {}],
    ['inventory.products.list', {}],
    ['households.family.get', {}],
    ['messages.conversations.list', {}],
    ['homecloud.files.list', {}],
  ]) {
    const r = await call(`/api/homi/v1/tools/${toolId}/invoke`, 'POST', args);
    const ok = r.status === 200 && r.payload?.tool_id === toolId && r.payload?.data;
    check('read_' + toolId, ok, 'status=' + r.status + (r.status !== 200 ? ' err=' + (r.payload?.error?.code || JSON.stringify(r.payload).slice(0, 120)) : ''));
  }

  // 4. input inválido
  const bad = await call('/api/homi/v1/tools/home.summary.get/invoke', 'POST', { campo_inexistente: 1 });
  check('input_invalido_rechazado', bad.status !== 200, 'status=' + bad.status);

  // 5. tool desconocida
  const unknown = await call('/api/homi/v1/tools/no.existe.tool/invoke', 'POST', {});
  check('tool_desconocida_rechazada', unknown.status !== 200, 'status=' + unknown.status);

  // 6. escritura real con proposal_id + verificación de persistencia
  const title = 'Tarea E2E HOMI ' + Date.now();
  const createRes = await fetch(BASE + '/api/homi/v1/internal/tools/planner.tasks.create/execute', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${TOKEN}`,
      'X-Homi-Internal-Write': process.env.HOMI_INTERNAL_WRITE_SECRET || 'local-dev-homi-internal-write-only',
    },
    body: JSON.stringify({ proposal_id: 'prop_e2e_' + Date.now(), args: { title } }),
  });
  const createText = await createRes.text();
  let createPayload; try { createPayload = JSON.parse(createText); } catch { createPayload = { raw: createText }; }
  const create = { status: createRes.status, payload: createPayload };
  const createdOk = create.status === 200 && create.payload?.ok === true;
  check('write_planner_task_create', createdOk, 'status=' + create.status + (createdOk ? '' : ' err=' + JSON.stringify(create.payload).slice(0, 200)));
  const createdId = create.payload?.result?.data?.id || create.payload?.result?.data?.task?.id;
  if (createdId) {
    const list = await call('/api/homi/v1/tools/planner.tasks.list/invoke', 'POST', {});
    const found = JSON.stringify(list.payload).includes(title);
    check('write_persistida_y_legible', found, 'task_id=' + createdId);
  } else {
    check('write_persistida_y_legible', false, 'sin id en respuesta: ' + JSON.stringify(create.payload).slice(0, 300));
  }

  // 7. seam interno sin secreto = 403
  const seam = await fetch(BASE + '/api/homi/v1/internal/tools/planner.tasks.create/execute', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify({ proposal_id: 'x', args: { title: 'x' } }),
  });
  check('seam_sin_secreto_403', seam.status === 403, 'status=' + seam.status);

  const pass = results.filter((r) => r.ok).length;
  console.log(`\nRESULT ${pass}/${results.length}`);
  process.exit(pass === results.length ? 0 : 1);
})();
