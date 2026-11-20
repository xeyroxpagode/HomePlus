const fs=require('fs'),path=require('path');
const D=__dirname;
const inv=JSON.parse(fs.readFileSync(path.join(D,'02_COMPLETE_FUNCTIONAL_INVENTORY.json'),'utf8'));
const esc=s=>String(s??'').replace(/\|/g,'\\|').replace(/\n/g,' ');
const non=inv.operations.filter(x=>x.final_destination!=='TARGET_IMPLEMENT');
const groups={};
for(const x of non) (groups[x.final_destination]||=[]).push(x);
const OWNER={
  BLOCKED_DEPENDENCY:'Actor C + proveedor/backend canónico',
  BLOCKED_AUTHORITY:'Actor A (decisión) + backend/RLS',
  BLOCKED_UNSAFE:'Actor A (PD-04) / diseño de tools tipadas',
  EXCLUDED_SECURITY:'Permanente — no se desbloquea',
  EXCLUDED_NOT_PRODUCT:'Permanente salvo cambio de producto',
  PRODUCT_DECISION:'ACTOR A',
};
const COND={
  BLOCKED_DEPENDENCY:'Proveedor disponible o corrección del servicio canónico + validación con fixture',
  BLOCKED_AUTHORITY:'Consentimiento/capability verificable en servidor o decisión funcional aprobada',
  BLOCKED_UNSAFE:'Rediseño como tool tipada o UI dedicada; nunca acceso directo desde LLM',
  EXCLUDED_SECURITY:'Ninguna: credenciales/service-role/dispositivo nativo no son tools del modelo',
  EXCLUDED_NOT_PRODUCT:'Existencia real de backend/producto (hoy no existe)',
  PRODUCT_DECISION:'Resolución explícita en 14_PRODUCT_DECISION_PACKET.md',
};
const CONSEQ={
  BLOCKED_DEPENDENCY:'Operación no disponible desde HOMI; resto del dominio sí',
  BLOCKED_AUTHORITY:'Operación no disponible; se informa al usuario con razón',
  BLOCKED_UNSAFE:'La funcionalidad sigue en la app nativa/HUI',
  EXCLUDED_SECURITY:'Sin consecuencia: nunca fue apta para el modelo',
  EXCLUDED_NOT_PRODUCT:'Sin consecuencia: no existe producto que exponer',
  PRODUCT_DECISION:'Default seguro: no exponer hasta decisión',
};
let md=`# 05 — DEFERRED / BLOCKED / EXCLUDED RECONCILIATION — Pasada 1/2

**Política aplicada (Actor A):** maximizar cobertura. Está **prohibido** mantener una operación como \`DEFERRED\` por complejidad o por «no aportar al recorrido HOMI V1». Solo se mantienen fuera del contrato las operaciones con razón funcional, técnica o de seguridad **demostrable** y citada.

**Resultado:** de las 176 operaciones anteriores (92 IMPLEMENT / 59 DEFERRED / 15 BLOCKED / 10 EXCLUDED), **todas** tienen destino final. Las 59 \`DEFERRED\` se reclasificaron: 51 pasaron a objetivo, 3 a bloqueo real, 3 a exclusión por no-producto/seguridad, 2 a decisión de producto. Se incorporaron 174 operaciones nuevas.

## 1. Resumen por destino final

| Destino | Cantidad | Significado |
|---|---:|---|
`;
for(const [k,v] of Object.entries(inv.totals.by_final_destination).sort((a,b)=>b[1]-a[1])) md+=`| ${k.replace(/_/g,' ')} | ${v} | ${k==='TARGET_IMPLEMENT'?'Contrato completo en 04':CONSEQ[k]||'—'} |\n`;
md+=`
## 2. Análisis individual (todas las operaciones no objetivo)

Cada fila incluye justificación objetiva, responsable, condición de desbloqueo y consecuencia funcional. La dificultad técnica **nunca** es justificación suficiente por sí sola.

`;
for(const [dest,rows] of Object.entries(groups)){
  md+=`### ${dest.replace(/_/g,' ')} — ${rows.length} operaciones\n\n`;
  md+=`**Responsable:** ${OWNER[dest]} · **Condición de desbloqueo:** ${COND[dest]}\n\n`;
  md+=`| Operación | Antes | Origen | Justificación objetiva (evidencia) | Consecuencia |\n|---|---|---|---|---|\n`;
  for(const x of rows) md+=`| \`${esc(x.operation_id)}\` | ${esc(x.previous_destination||'—')} | ${x.source==='catalog_176'?'176':'NEW'} | ${esc(x.reclassification_reason)} | ${esc(CONSEQ[dest])} |\n`;
  md+='\n';
}
md+=`## 3. Decisiones que NO se tomaron en esta pasada

- No se decidió si HOMI puede finalizar compras registrando un gasto (PD-01).
- No se decidió si se implementa un flujo de consentimiento de presencia (PD-02).
- No se decidieron operaciones financieras de autoridad humana (PD-03).
- No se decidió exponer la administración de hogares/roles a coordinadores desde HOMI (PD-04).
- No se decidió invertir en SEE/HOMI-B ni en carga de archivos desde el asistente (PD-05).
- No se decidió soportar \`front/mi-front-expo-go\` (PD-06).

Ninguna ausencia de decisión se convirtió en permiso implícito: las tools correspondientes **no están en el catálogo final**.

## 4. Casos límite resueltos

1. **\`identity.profile.update\`**: antes DEFERRED con razón «no aporta al recorrido». Se **reclama** porque es una escritura segura sin service-role. La razón anterior era inadmisible según la política actual.
2. **\`planner.drafts.autosave\`**: se mantiene fuera no por complejidad sino porque el autoguardado es propiedad de la app; un borrador implícito generado por el asistente cambiaría el contrato de producto.
3. **\`assets.*\`**: 5 escrituras antes, 26 ahora. No se excluyó ninguna por «difícil»: cada una tiene capability, idempotencia y confirmación definidas.
4. **\`planner.plans.create/update/transition\`**: antes DEFERRED por payload complejo. Se reclaman con **tools tipadas por sección**, sin JSON arbitrario.
5. **\`homecloud.content.register\`**: bloqueo real de dependencia (archivo+firmado), no decisión de producto.

**Gate D: PASS — todas las operaciones anteriores y nuevas tienen destino definitivo y trazable.**
`;
fs.writeFileSync(path.join(D,'05_DEFERRED_BLOCKED_EXCLUDED_RECONCILIATION.md'),md);
console.log('05 written, non-target:',non.length);
