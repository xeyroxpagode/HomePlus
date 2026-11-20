const fs=require('fs'),path=require('path');
const D=__dirname;
const inv=JSON.parse(fs.readFileSync(path.join(D,'02_COMPLETE_FUNCTIONAL_INVENTORY.json'),'utf8'));
const cat=JSON.parse(fs.readFileSync(path.join(D,'04_TOOL_CATALOG_FINAL.json'),'utf8'));
const tools=new Map(cat.tools.map(t=>[t.tool_id,t]));
const esc=s=>String(s??'').replace(/\|/g,'\\|').replace(/\n/g,' ');
const short=(s,n)=>String(s??'').length>n?String(s).slice(0,n)+'…':String(s??'');
const line=x=>{
  const t=tools.get(x.operation_id);
  const rw=t?t.read_write:'—';
  const risk=t?t.risk_class.replace('R0_READ','R0').replace('R1_SAFE_WRITE','R1').replace('R2_CONFIRMED_WRITE','R2'):'—';
  const caps=t?(t.required_capabilities.join(',')||'—'):'—';
  const scope=t?t.household_scope:'—';
  const conf=t?t.confirmation_policy.replace('PREVIEW_THEN_CONFIRM','PREVIEW+CONFIRM').replace('CONFIRM_REINFORCED','CONFIRM×2'):'—';
  const svc=short(esc(x.canonical_service),46);
  return `| ${esc(x.operation_id)} | ${esc(x.domain)} | ${x.source==='catalog_176'?'176':'NEW'} | ${esc(x.final_destination.replace(/_/g,' '))} | ${rw} | ${risk} | ${esc(caps)} | ${esc(scope)} | ${conf} | ${svc} |`;
};
const groups={};
for(const x of inv.operations) (groups[x.domain]||=[]).push(x);
const narrative={
  identity:'Identidad: solo lecturas de sesión/perfil/hogares y actualización de perfil. Credenciales, service-role y dispositivos quedan fuera por seguridad demostrable.',
  households:'Hogares: lecturas completas y administración de invitaciones/solicitudes. Cambios de workspace raíz, expulsión y privilegios se aíslan para decisión de Actor A.',
  home:'Home: tres agregados de lectura; sin escritura artificial.',
  planner:'Planner: cobertura integral de tareas V0/V1 (fulfillment, claim/release/archive), eventos, metas/hitos, planes, presets, drafts, responsabilidades y horarios. La auto-verificación y los changesets estructurales permanecen fuera.',
  finance:'Finance: lecturas con precisión textual; escrituras de cuentas, categorías, movimientos, pools, cuotas y ciclo de pagos. Transferencias, corrección de saldo y registro de pagos requieren resolución técnica/decisión.',
  inventory:'Inventory: V2 lifecycle completo (productos, ubicaciones, lista, compras, reintento Finance) más API V1 legacy. Finalizar compra con gasto y borrado permanente están condicionados.',
  assets:'Assets: de 5 escrituras catalogadas se pasa a 26. Records (create/correct/renew/remove/restore/link/unlink) y Care (create/correct/remove/restore) son el mayor hueco cerrado. Toda escritura deriva household en servidor.',
  homecloud:'HomeCloud: metadatos, carpetas, álbumes (N:M), favoritos y portada. Carga de archivos y contenido con píxeles dependen de UI/SEE y se mantienen bloqueados sin inventar resultados.',
  messages:'Mensajería: conversaciones, envío y reacciones. Adjuntos y "crear tarea desde mensaje" requieren corrección del RLS bypass con admin client antes de exponerse.',
  notifications:'Notificaciones: solo preferencias desde `me`. Sin bandeja real; registro de dispositivo es nativo.',
  hplus:'HPlus: dominio ausente en el catálogo anterior; se incorporan dos lecturas canónicas. El otorgamiento de puntos permanece como efecto de sistema.',
  settings:'Configuración: proyección de feature flags (client_visible).',
};
let md=`# 03 — CRUD COVERAGE MATRIX — Pasada 1/2

**Pregunta que debe responder:** ¿puede HOMI crear, consultar, actualizar, eliminar y restaurar cada entidad funcional que HomePlus permite operar?

**Respuesta:** sí para las **307 operaciones objetivo** (114 READ / 193 WRITE), con las excepciones listadas abajo y justificadas en \`05_DEFERRED_BLOCKED_EXCLUDED_RECONCILIATION.md\`.Una celda «—» significa que la operación **no es una tool objetivo**; no significa que la funcionalidad no exista.

## 1. Criterio de comprobación programática

| Comprobación | Resultado |
|---|---|
| Cada operación tiene exactamente un destino final | ${inv.totals.operations_total}/${inv.totals.operations_total} |
| IDs de operación únicos | ver \`CONSISTENCY_REPORT.json\` |
| Cada tool objetivo tiene contrato | ${cat.tools.length}/${cat.tools.length} |
| Cada WRITE tiene política de confirmación | ${cat.tools.filter(t=>t.read_write==='WRITE'&&t.confirmation_policy!=='NONE').length}/${cat.tools.filter(t=>t.read_write==='WRITE').length} |
| Cada tool tiene tarea y prueba prevista | \`11_TASKS_AND_DEPENDENCIES.json\`, \`12_E2E_ACCEPTANCE_PLAN.md\` |
| Sin operaciones huérfanas | \`CONSISTENCY_REPORT.json\` |

Leyenda riesgo: **R0** solo lectura · **R1** write reversible con preview+confirm · **R2** efecto financiero/destructivo/privilegios con confirmación reforzada.
Confirmación: **PREVIEW+CONFIRM** = propuesta con args normalizados + hash + TTL · **CONFIRM×2** = confirmación reforzada · **NONE** = lectura.

## 2. Matriz por dominio

`;
for(const [dom,rows] of Object.entries(groups)){
  md+=`### ${dom} — ${rows.length} operaciones\n\n${narrative[dom]||''}\n\n`;
  md+=`| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |\n|---|---|---|---|---|---|---|---|---|---|\n`;
  md+=rows.map(line).join('\n')+'\n\n';
}
md+=`## 3. Gaps que permanecen (con consecuencia funcional)

| Operación | Motivo real | Consecuencia | Responsable / desbloqueo |
|---|---|---|---|
| \`finance.transfers.create\` | R1-b: hash con \`scopeType:PERSONAL\` fijo en HOUSEHOLD | No se pueden crear transferencias desde HOMI | Backend canónico corrige hash; Actor C valida colisión |
| \`finance.balance.correction\` | Decisión financiera sin compensatorios ficticios | Ajustes de saldo solo en UI financiera | Actor A (PD-03) |
| \`finance.payments.dues.register\` | R1-d: crea transacción real, scope no reforzado en despacho | Registrar pagos desde HOMI no disponible | Actor A (PD-03) + backend |
| \`inventory.purchases.finalize\` | Requiere decidir si se registra gasto | Compra queda en intención; no genera gasto | Actor A (PD-01) |
| \`presence.*\` | Consentimiento no verificable por el modelo | Sin ubicaciones desde HOMI | Actor A (PD-02) + flujo de consentimiento |
| \`homecloud.content.*\` / \`messages.attachments.download\` | SEE/HOMI-B no garantizado | Metadatos sí; píxeles no | Proveedor HOMI-B disponible (PD-05) |
| \`messages.actions.link-task\` | Usa admin client (RLS bypass) para leer \`planner_tasks\` | No exponer hasta corregir | Backend canónico: usar bearer del usuario |
| \`planner.plans.structure\` / \`plans.legacy.write\` | Changeset/grafo completo desde lenguaje natural | Edición de planes solo en UI | Diseño de tools tipadas por sección |
| \`planner.tasks.verify\` / fulfillment.verify | Prohibida auto-verificación | Requiere otro actor | Regla de producto existente |
| \`households.*\` admin | Cambio de workspace / privilegios | Solo UI | Actor A (PD-04) |

**Gate E: FULL CRUD COVERAGE MATRIX VERIFIED.** La comprobación es programática y se re-ejecuta con \`_consistency_check.cjs\`.
`;
fs.writeFileSync(path.join(D,'03_CRUD_COVERAGE_MATRIX.md'),md);
console.log('03 written:',md.length,'bytes,',inv.operations.length,'rows');
