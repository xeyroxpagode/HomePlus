// Regenera backend/src/homi/v1/tool_catalog.json desde 04_TOOL_CATALOG_FINAL.json.
// Tickets: validación de esquema, digest, y honestidad de authority.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const D = __dirname;
const finalCatalog = JSON.parse(fs.readFileSync(path.join(D, '04_TOOL_CATALOG_FINAL.json'), 'utf8'));
const out = path.join(D, '..', '..', '..', '..', 'backend', 'src', 'homi', 'v1', 'tool_catalog.json');
const finalCatalogForWriting = {
  schema_version: finalCatalog.schema_version || '2.0.0',
  generated_at: new Date().toISOString(),
  target: finalCatalog.target,
  authority: finalCatalog.policy,
  summary: {
    ...finalCatalog.summary,
    // Contrato que consume catalog.js (`implemented_tools`) + metadatos del gateway
    implemented_tools: finalCatalog.summary.target_tools,
    operations_total: finalCatalog.summary.operations_total,
  },
  destination_legend: {
    IMPLEMENT: 'Herramienta activa: binding, validación, autorización y tests validados.',
    PRODUCT_DECISION: 'Pendiente decisión de Actor A; default seguro.',
    BLOCKED_DEPENDENCY: 'Bloqueado por dependencia real; no exponer por ahora.',
    BLOCKED_AUTHORITY: 'Bloqueado por autoridad/consentimiento.',
    BLOCKED_UNSAFE: 'Bloqueado por inseguridad demostrable.',
    EXCLUDED_SECURITY: 'Excluido por seguridad; no se offer al modelo.',
    EXCLUDED_NOT_PRODUCT: 'Excluido: no es funcionalidad de producto.',
  },
  tools: finalCatalog.tools.map((t) => {
    const outTool = {
      ...t,
      risk_flags: t.risk_flags || (t.read_write === 'WRITE' ? ['LOW_MUTATION'] : ['READ_ONLY']),
    };
    // Validar esquema de inputs contra el subset soportado por argumentValidator.js
    return outTool;
  }),
};
// Validar schemas contra el validador de argumentos del gateway
// (subconjunto: string/integer/boolean/number/array/object).
const backendValidator = require('../../../../backend/src/homi/v1/argumentValidator.js');
const STR_SAMPLE_CANDIDATES = ['2026-11-19', '2026-11', '2026-01', '2026-01-01', '09:00', 'ABC', 'a', '1', '0', '2026', '0.00', 'x', 'y'];
let invalid = [];
for (const t of finalCatalogForWriting.tools) {
  const sampleArgs = {};
  for (const [f, s] of Object.entries(t.input_schema.properties || {})) {
    const v = sampleFor(s);
    if (v !== undefined) sampleArgs[f] = v;
  }
  try {
    backendValidator.validateToolArguments(t.input_schema, sampleArgs);
    // Regresión negativa: campo desconocido debe rechazarse siempre.
    backendValidator.validateToolArguments(t.input_schema, { ...sampleArgs, __unknown_field: 'x' });
    invalid.push(`${t.tool_id}: unknown field __unknown_field was accepted`);
  } catch (e) {
    if (!(e.code === 'HOMI_TOOL_ARGUMENT_INVALID' && e.details && e.details.field === '__unknown_field')) {
      invalid.push(`${t.tool_id}: ${e.message}`);
    }
  }
}
const pathOut = path.resolve(out);
fs.mkdirSync(path.dirname(pathOut), { recursive: true });
fs.writeFileSync(pathOut, JSON.stringify(finalCatalogForWriting, null, 2) + '\n');
console.log('wrote', pathOut, 'tools:', finalCatalogForWriting.tools.length);
if (invalid.length) { console.log('INVALID SCHEMA:', invalid); }

function sampleFor(schema) {
  if (!schema) return undefined;
  const t = schema.type;
  if (schema.enum && schema.enum.length > 0) return schema.enum[0];
  if (t === 'string') {
    const min = schema.minLength || 0;
    const max = schema.maxLength || 1000;
    if (schema.pattern) {
      const re = new RegExp(schema.pattern);
      for (const c of STR_SAMPLE_CANDIDATES) {
        if (c.length >= min && c.length <= max && re.test(c)) return c;
      }
    }
    return 'x'.repeat(Math.max(min, 1));
  }
  if (t === 'integer') return 1;
  if (t === 'number') return 1;
  if (t === 'boolean') return true;
  if (t === 'array') return schema.items ? [sampleFor(schema.items)] : [];
  if (t === 'object') {
    const o = {};
    for (const k of (schema.required || [])) {
      const v = sampleFor((schema.properties || {})[k] || {});
      if (v !== undefined) o[k] = v;
    }
    return o;
  }
  return undefined;
}
