// Script de análisis SOLO LECTURA del catálogo anterior (03_TOOL_CATALOG.json).
// No muta código, datos ni runtime. Uso: node _analyze_catalog.cjs <path-to-catalog>
const fs = require('fs');
const path = process.argv[2];
const c = JSON.parse(fs.readFileSync(path, 'utf8'));

const ops = [];
for (const d of c.domains) {
  for (const o of d.operations) ops.push({ ...o, domain: d.domain });
}

const count = (arr, key) => arr.reduce((m, x) => { const k = x[key] ?? '(none)'; m[k] = (m[k] || 0) + 1; return m; }, {});

console.log('=== TOTALES ===');
console.log('operations:', ops.length, 'tools:', c.tools.length);
console.log('domains:', c.domains.length);

console.log('\n=== OPERACIONES POR DESTINO ===');
console.log(JSON.stringify(count(ops, 'destination'), null, 2));
console.log('\n=== OPERACIONES POR risk_class ===');
console.log(JSON.stringify(count(ops, 'risk_class'), null, 2));
console.log('\n=== OPERACIONES POR DOMINIO x DESTINO ===');
const byDom = {};
for (const o of ops) {
  byDom[o.domain] ||= { total: 0, IMPLEMENT: 0, DEFERRED: 0, BLOCKED: 0, EXCLUDED: 0, OTHER: 0 };
  byDom[o.domain].total++;
  if (byDom[o.domain][o.destination] !== undefined) byDom[o.domain][o.destination]++;
  else byDom[o.domain].OTHER++;
}
console.log(JSON.stringify(byDom, null, 2));

console.log('\n=== TOOLS POR DOMINIO ===');
console.log(JSON.stringify(count(c.tools, 'domain'), null, 2));
console.log('\n=== TOOLS POR risk_class ===');
console.log(JSON.stringify(count(c.tools, 'risk_class'), null, 2));
console.log('\n=== TOOLS POR confirmation_policy ===');
console.log(JSON.stringify(count(c.tools, 'confirmation_policy'), null, 2));

const reads = c.tools.filter(t => String(t.risk_class).includes('READ'));
const writes = c.tools.filter(t => !String(t.risk_class).includes('READ'));
console.log('\n=== READ/WRITE ===');
console.log('READ tools:', reads.length, 'WRITE tools:', writes.length);
console.log('WRITE tool ids:', writes.map(t => t.tool_id).join(', '));

console.log('\n=== DUPLICADOS ===');
const opIds = ops.map(o => o.operation_id);
const toolIds = c.tools.map(t => t.tool_id);
const dups = a => a.filter((x, i) => a.indexOf(x) !== i);
console.log('dup operation_id:', JSON.stringify(dups(opIds)));
console.log('dup tool_id:', JSON.stringify(dups(toolIds)));

console.log('\n=== OPERACIONES IMPLEMENT SIN TOOL ===');
const implOps = ops.filter(o => o.destination === 'IMPLEMENT').map(o => o.operation_id);
console.log(JSON.stringify(implOps.filter(id => !toolIds.includes(id))));

console.log('\n=== TOOLS SIN OPERACION IMPLEMENT ===');
console.log(JSON.stringify(toolIds.filter(id => !implOps.includes(id))));

console.log('\n=== INVENTARIO COMPLETO DE OPERACIONES ===');
for (const o of ops) {
  console.log([o.operation_id, o.domain, o.destination, o.risk_class, o.confirmation_policy, o.http?.method || '', o.http?.path || '', o.canonical_service || '', (o.evidence_reason || '').slice(0, 120)].join('\t'));
}
