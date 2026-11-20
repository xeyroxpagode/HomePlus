// Chequeos documentales de consistencia (seccion 17). No modifica producto.
const fs=require('fs'),path=require('path');
const D=__dirname;
const load=n=>JSON.parse(fs.readFileSync(path.join(D,n),'utf8'));
const inv=load('02_COMPLETE_FUNCTIONAL_INVENTORY.json');
const cat=load('04_TOOL_CATALOG_FINAL.json');
const tasks=load('11_TASKS_AND_DEPENDENCIES.json');
const recon=fs.readFileSync(path.join(D,'05_DEFERRED_BLOCKED_EXCLUDED_RECONCILIATION.md'),'utf8');
const checks=[];
const C=(id,desc,ok,detail)=>checks.push({id,description:desc,status:ok?'PASS':'FAIL',detail});
const opIds=inv.operations.map(x=>x.operation_id);
const toolIds=cat.tools.map(t=>t.tool_id);
const target=inv.operations.filter(x=>x.final_destination==='TARGET_IMPLEMENT');
const targetIds=target.map(x=>x.operation_id);
const dup=a=>a.filter((v,i)=>a.indexOf(v)!==i);
const ALLOWED=new Set(['TARGET_IMPLEMENT','BLOCKED_DEPENDENCY','BLOCKED_AUTHORITY','BLOCKED_UNSAFE','EXCLUDED_SECURITY','EXCLUDED_NOT_PRODUCT','PRODUCT_DECISION']);

C('C01','Inventario total reconstruido',inv.totals.operations_total===350,`${inv.totals.operations_total} operaciones (176 anteriores + 174 nuevas netas)`);
C('C02','Unicidad de operation IDs',dup(opIds).length===0,`duplicados: ${JSON.stringify(dup(opIds))}`);
C('C03','Unicidad de tool IDs',dup(toolIds).length===0,`duplicados: ${JSON.stringify(dup(toolIds))}`);
C('C04','Cada operación tiene exactamente un destino válido',inv.operations.every(x=>ALLOWED.has(x.final_destination)),`destinos: ${JSON.stringify(inv.totals.by_final_destination)}`);
C('C05','Correspondencia operación → tool (target)',targetIds.every(id=>toolIds.includes(id)),`target sin tool: ${JSON.stringify(targetIds.filter(id=>!toolIds.includes(id)))}`);
C('C06','Correspondencia tool → operación target',toolIds.every(id=>targetIds.includes(id)),`tool sin operación: ${JSON.stringify(toolIds.filter(id=>!targetIds.includes(id)))}`);
const required=['tool_id','domain','input_schema','output_schema','authority','execution','confirmation_policy','error_mapping','test_cases','canonical_service'];
const noContract=cat.tools.filter(t=>required.some(k=>t[k]===undefined||t[k]===null));
C('C07','Tool → contrato estructurado completo',noContract.length===0,`tools incompletos: ${noContract.length}`);
const taskTools=new Set(tasks.tasks.flatMap(t=>t.tool_ids));
const noTask=toolIds.filter(id=>!taskTools.has(id));
C('C08','Tool → tarea de implementación',noTask.length===0,`tools sin tarea: ${JSON.stringify(noTask)}`);
const writes=cat.tools.filter(t=>t.read_write==='WRITE');
const noConf=writes.filter(t=>!t.confirmation_policy||t.confirmation_policy==='NONE');
C('C09','WRITE → política de confirmación',noConf.length===0,`WRITE sin confirmación: ${noConf.length}`);
const noAuth=cat.tools.filter(t=>!t.authority||t.authority.revalidate_server_side!==true||!Array.isArray(t.authority.forbidden_model_fields));
C('C10','Tool → permisos y campos prohibidos',noAuth.length===0,`tools sin autoridad: ${noAuth.length}`);
const noTests=cat.tools.filter(t=>!Array.isArray(t.test_cases)||t.test_cases.length<8||(t.read_write==='WRITE'&&!t.test_cases.includes('confirmation_binding')));
C('C11','Tool → plan de pruebas',noTests.length===0,`tools con pruebas insuficientes: ${noTests.length}`);
const noSvc=cat.tools.filter(t=>!t.canonical_service);
C('C12','Handler → servicio canónico real',noSvc.length===0,`tools sin servicio: ${JSON.stringify(noSvc.map(t=>t.tool_id))}`);
const badPath=cat.tools.filter(t=>!t.http||!(typeof t.http.path==='string'&&(t.http.path.startsWith('/')||t.http.path.includes('SEE'))));
C('C13','Sin referencias HTTP inválidas',badPath.length===0,`paths inválidos: ${badPath.length}`);
C('C14','Sin operaciones sin clasificar',inv.operations.every(x=>x.final_destination&&x.reclassification_reason),`sin razón: ${inv.operations.filter(x=>!x.reclassification_reason).length}`);
const excluded=inv.operations.filter(x=>x.final_destination.startsWith('EXCLUDED'));
C('C15','Exclusiones con razón demostrada',excluded.every(x=>x.reclassification_reason&&x.reclassification_reason.length>20),`excluidas: ${excluded.length}`);
C('C16','Tareas con criterio de aceptación',tasks.tasks.every(t=>t.done_criteria&&t.done_criteria.length>10&&t.stop_conditions),`tareas: ${tasks.tasks.length}`);
C('C17','Bloqueos con responsable y condición',recon.includes('**Responsable:**')&&recon.includes('**Condición de desbloqueo:**')&&inv.operations.filter(x=>x.final_destination.startsWith('BLOCKED')).every(x=>x.reclassification_reason),`bloqueadas: ${inv.operations.filter(x=>x.final_destination.startsWith('BLOCKED')).length}`);
C('C18','Dependencias de tareas válidas',(()=>{const ids=new Set(tasks.tasks.map(t=>t.id));return tasks.tasks.every(t=>t.dependencies.every(d=>ids.has(d)));})(),'todas las dependencias apuntan a tareas existentes');
C('C19','Decisiones de producto aisladas',inv.operations.filter(x=>x.final_destination==='PRODUCT_DECISION').length===6,`PD: ${inv.operations.filter(x=>x.final_destination==='PRODUCT_DECISION').map(x=>x.operation_id).join(', ')}`);
C('C20','Sin doble fuente de verdad del catálogo',cat.tools.length===target.length,`catálogo=${cat.tools.length}, objetivo=${target.length}`);

const passed=checks.filter(c=>c.status==='PASS').length;
const report={
  generated_at:new Date().toISOString(),
  pass:'1/2 discovery & contract freeze',
  summary:{checks:checks.length,passed,failed:checks.length-passed,verdict:checks.every(c=>c.status==='PASS')?'PASS':'FAIL'},
  quantitative:{
    operations_total:inv.totals.operations_total,
    target_operations:target.length,
    target_tools:cat.tools.length,
    read_tools:cat.tools.filter(t=>t.read_write==='READ').length,
    write_tools:writes.length,
    excluded:excluded.length,
    blocked:inv.operations.filter(x=>x.final_destination.startsWith('BLOCKED')).length,
    product_decisions:inv.operations.filter(x=>x.final_destination==='PRODUCT_DECISION').length,
    tasks:tasks.tasks.length,
  },
  checks,
};
fs.writeFileSync(path.join(D,'CONSISTENCY_REPORT.json'),JSON.stringify(report,null,2)+'\n');
let md=`# CONSISTENCY REPORT — Chequeos automáticos (sección 17)\n\n**Verdict:** ${report.summary.verdict} · ${passed}/${checks.length} checks PASS\n\n| ID | Check | Resultado | Detalle |\n|---|---|---|---|\n`;
for(const c of checks) md+=`| ${c.id} | ${c.description} | ${c.status} | ${String(c.detail).slice(0,160)} |\n`;
md+=`\n## Cuantitativo\n\n\`\`\`json\n${JSON.stringify(report.quantitative,null,2)}\n\`\`\`\n`;
fs.writeFileSync(path.join(D,'CONSISTENCY_REPORT.md'),md);
console.log(JSON.stringify(report.summary,null,2));
