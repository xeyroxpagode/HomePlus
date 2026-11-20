const fs=require('fs'),path=require('path');
const D=__dirname;
const cat=JSON.parse(fs.readFileSync(path.join(D,'04_TOOL_CATALOG_FINAL.json'),'utf8'));
const byDom={};
for(const t of cat.tools) (byDom[t.domain]||=[]).push(t.tool_id);
const tasks=[];
const add=(id,domain,deps,objective,files,tool_ids,tests,evidence,stop,done)=>tasks.push({
  id,domain,dependencies:deps,objective,files_implicated:files,tool_ids,
  contracts:`04_TOOL_CATALOG_FINAL.json â†’ tools[${tool_ids.length}]`,
  permissions:'Ver 06_AUTHORITY_AND_CONFIRMATION_MATRIX.md; capability re-verificada server-side',
  tests,evidence_expected:evidence,stop_conditions:stop,done_criteria:done,
});

add('T-FOUND-01','foundation',[],'Regenerar catÃ¡logo de runtime y anclas SHA desde 04_TOOL_CATALOG_FINAL.json (307 tools).',
  ['backend/src/homi/v1/tool_catalog.json','homi-orchestrator/catalog/*.json','backend/src/homi/v1/catalog.js'],
  cat.tools.map(t=>t.tool_id),'catalog.test.js: unicidad, esquemas, digest, 307/307',
  'digest nuevo impreso en health; 0 tool sin contrato',
  'Si el loader rechaza el catÃ¡logo por ancla vieja, detener y recalcular antes de seguir.',
  'GET /api/homi/v1/health reporta 307 tools y el digest coincide con el archivo.');
add('T-FOUND-02','foundation',['T-FOUND-01'],'Registrar bindings estÃ¡ticos por tool_id (require estÃ¡tico, sin require dinÃ¡mico ni ejecutor genÃ©rico).',
  ['backend/src/homi/generatedBindings.js','backend/src/homi/v1/toolRegistry.js'],
  cat.tools.map(t=>t.tool_id),'bindings.test.js: cada tool resuelve a un binding; WRITE rechazado sin proposal_id',
  '0 bindings huÃ©rfanos; 0 require dinÃ¡mico',
  'Si un tool no tiene servicio canÃ³nico real, BLOCKED y fuera del registro.',
  'Los 307 tools tienen binding comprobable contra module.exports.');
add('T-FOUND-03','foundation',['T-FOUND-02'],'Ampliar HOMI-D a contratos de propuesta para las 193 WRITE (hoy solo 5).',
  ['homi-orchestrator/homi_tool_proposal.py','homi-orchestrator/homi_tool_write_execution.py','homi-orchestrator/catalog/*.json'],
  cat.tools.filter(t=>t.read_write==='WRITE').map(t=>t.tool_id),
  'pytest: propuesta por familia, hash de args, TTL, edit/cancel, confirm/execute binding',
  '193/193 WRITE con propuesta tipada; 0 JSON arbitrario del modelo',
  'Si una WRITE no tiene validators tipados, no habilitar su seam.',
  'Cada WRITE genera propuesta con args normalizados y hash; confirm antigua queda invÃ¡lida.');
add('T-FOUND-04','foundation',[],'Hacer autocontenida la suite D: portar tests/support.py, resolver plantilla PY en test_t13, separar tests T31/STT cancelados y proveer fixtures BD aisladas.',
  ['homi-orchestrator/tests/support.py','homi-orchestrator/tests/test_t13_context_builder.py','tests/run.js'],
  [],'pytest -q (suite V1): 0 errores de collection; fixtures sin BD productiva',
  'suite V1 verde; T31/STT marcados skip explÃ­cito',
  'No borrar ni relajar aserciones de autoridad; solo corregir infraestructura.',
  'pytest V1 termina sin collection errors y sin dependencias de BD productiva.');
add('T-FOUND-05','foundation',['T-FOUND-01'],'Cerrar el seam write: exigir estado de propuesta confirmada y hash de argumentos vigente antes de ejecutar; enviar If-Match/expected_version.',
  ['backend/src/controllers/homiV1.controller.js','backend/src/homi/v1/executor.js'],
  cat.tools.filter(t=>t.read_write==='WRITE').map(t=>t.tool_id),
  'internal-execute.test.js: propuesta no confirmadaâ†’403, args cambiadosâ†’409, versiÃ³n viejaâ†’412',
  'sin ejecuciÃ³n sin confirmaciÃ³n vigente',
  'Si el servicio canÃ³nico no acepta If-Match, documentar y usar expected_version en body; nunca degradar silenciosamente.',
  'Seam rechaza propuesta no confirmada y argumentos alterados.');

const order=['identity','households','home','planner','finance','inventory','assets','homecloud','messages','notifications','hplus','settings'];
let dep=['T-FOUND-05'];
for(const dom of order){
  const ids=byDom[dom]||[];
  if(!ids.length) continue;
  const id=`T-${dom.toUpperCase().replace('-','_')}-01`;
  const reads=cat.tools.filter(t=>t.domain===dom&&t.read_write==='READ').map(t=>t.tool_id);
  const writes=cat.tools.filter(t=>t.domain===dom&&t.read_write==='WRITE').map(t=>t.tool_id);
  add(id,dom,dep.slice(),`Implementar y validar los ${ids.length} tools de ${dom} (${reads.length} READ / ${writes.length} WRITE) contra servicios canÃ³nicos.`,
    [`backend/src/homi/v1/handlers/${dom}.js`,`backend/tests/homi/${dom}.*.test.js`,`front/mi-front-limpio/services/homi/`],
    ids,`E2E por tool: happy path, invÃ¡lido, capability denied, otro hogar, sesiÃ³n expirada, persistencia WRITE, ledger`,
    `${dom}: 200/201 real con BD aislada; WRITE verificado por lectura posterior`,
    `Si un endpoint canÃ³nico devuelve 410/404, bloquear el tool y documentar antes de continuar.`,
    `${ids.length}/${ids.length} tools con test focal PASS y evidencia de persistencia en WRITE.`);
  dep=[id];
}
add('T-CROSS-01','cross_module',['T-PLANNER-01','T-INVENTORY-01','T-FINANCE-01','T-ASSETS-01','T-MESSAGES-01'],
  'Implementar recorridos compuestos tipados (Assetsâ†’Planner, Inventarioâ†’Planner, Mensajeâ†’Tarea) con permisos de ambos dominios y compensaciones explÃ­citas.',
  ['homi-orchestrator/homi_tool_compound_result_contract.py','backend/src/homi/v1/executor.js'],
  ['assets.planner-items.create','inventory.shopping-list.to-planner-task'],
  'compound.test.js: fallo parcial, doble capability, origen origin_*, sin duplicados',
  'compensaciones documentadas; sin escrituras duplicadas',
  'messages.actions.link-task sigue BLOCKED por RLS bypass: no habilitar hasta correcciÃ³n.',
  'Recorridos con doble capability verificada y fallo parcial registrado.');
add('T-FRONT-01','frontend',['T-FOUND-03'],'Superficie HOMI definitiva: tile "MÃ¡s â†’ Homie", composer editable, propuestas con edit/cancel, transcripciÃ³n editable, sin TTS.',
  ['front/mi-front-limpio/screens/homi/HomiScreen.tsx','front/mi-front-limpio/components/homi/HomiSurface.tsx','front/mi-front-limpio/src/voice/'],
  [],'tsc --noEmit; contratos voz/transporte 10/10; teclado/safe-area/accessibilidad',
  'NEEDS DEVICE QA (Actor A) documentado, no PASS falso',
  'No portar T31/LiveKit/VAD/TTS; si aparece dependencia T31, detener.',
  'tsc limpio, contratos PASS, guion T32 Â§12 entregado a Actor A.');
add('T-E2E-01','e2e',dep.concat(['T-CROSS-01','T-FRONT-01']),
  'E2E real completo clienteâ†’gatewayâ†’Dâ†’THINKâ†’toolsâ†’BD aislada, por herramienta/rol/escenario.',
  ['backend/tests/homi/v1-e2e-smoke.js','docs/homi/full-integration/closure-discovery/12_E2E_ACCEPTANCE_PLAN.md'],
  [],'matriz 12_E2E; persistencia verificada; multi-rol con fixtures reales',
  'sin HTTP 200 como Ãºnica prueba; sin mock para certificar',
  'Si THINK/STT/SEE estÃ¡n DOWN, reportar BLOCKED con evidencia; no simular PASS.',
  'E2E PASS de los recorridos disponibles; BLOCKED justificados para el resto.');
add('T-ACCEPT-01','acceptance',['T-E2E-01'],'AutocorrecciÃ³n y aceptaciÃ³n tÃ©cnica: re-ejecutar consistencia, regresiones y revisar contradicciones.',
  ['docs/homi/full-integration/closure-discovery/CONSISTENCY_REPORT.json'],
  [],'npm run quality + consistency + diff --check',
  '0 contradicciones graves abiertas; veredicto final',
  'Si aparece un ID duplicado o tool sin contrato, bloquear aceptaciÃ³n.',
  'Reporte cuantitativo PASS y veredicto emitido por Actor A.');

const doc={schema_version:'1.0.0',generated_at:new Date().toISOString(),pass:'2/2 implementation',
  policy:'Tareas atÃ³micas con dependencias, contratos, permisos, tests, evidencia, stop conditions y criterio de terminado.',
  totals:{tasks:tasks.length,by_domain:tasks.reduce((m,t)=>{m[t.domain]=(m[t.domain]||0)+1;return m;},{}),tools_covered:new Set(tasks.flatMap(t=>t.tool_ids)).size},
  tasks};
fs.writeFileSync(path.join(D,'11_TASKS_AND_DEPENDENCIES.json'),JSON.stringify(doc,null,2)+'\n');
console.log(JSON.stringify(doc.totals,null,2));

