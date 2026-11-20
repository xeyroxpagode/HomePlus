// Regenera homi-orchestrator/catalog/homi-tools.v2.json desde 04_TOOL_CATALOG_FINAL.json
// Seguindo el formato esperado por homi_tool_catalog.py (schema_version, source_*, tools[{tool_id, kind, confirmation, riskFlags, inputSchema, outputSchema, description}]).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const D = __dirname;
const finalCatalog = JSON.parse(fs.readFileSync(path.join(D, '04_TOOL_CATALOG_FINAL.json'), 'utf8'));

const tools = finalCatalog.tools
  .map((t) => ({
  tool_id: t.tool_id,
  contract_version: '2.0.0',
  kind: t.read_write === 'WRITE' ? 'WRITE' : 'READ',
  confirmation: t.confirmation_policy === 'NONE' ? 'NEVER' : 'REQUIRED',
  description: t.description,
  riskFlags: t.risk_class === 'R0_READ' ? ['READ_ONLY'] : ['LOW_MUTATION'],
  inputSchema: t.input_schema,
  outputSchema: t.output_schema || { type: 'object', additionalProperties: true, properties: { data: { type: 'object' }, meta: { type: 'object' } } },
}))
  .sort((a, b) => (a.tool_id < b.tool_id ? -1 : a.tool_id > b.tool_id ? 1 : 0));

const doc = {
  schema_version: '2.0.0',
  source_branch: finalCatalog.target.worktree_branch,
  source_commit: finalCatalog.target.commit,
  source_repository: finalCatalog.target.repo,
  tool_contract_version: '2.0.0',
  pass: '2/2 implementation',
  policy: 'Catálogo definitivo: todas las herramientas objetivo (307). El catálogo del gateway es la fuente de verdad; D proyecta el mismo contrato.',
  tools,
};
const jsonPath = path.resolve(path.join(D, '..', '..', '..', '..', 'homi-orchestrator', 'catalog', 'homi-tools.v2.json'));
const raw = JSON.stringify(doc, null, 2) + '\n';
fs.writeFileSync(jsonPath, raw);
const digest = crypto.createHash('sha256').update(raw).digest('hex').toUpperCase();
fs.writeFileSync(jsonPath.replace('.json', '.sha256.txt'), digest + '\n');
console.log('wrote', jsonPath, 'tools:', tools.length, 'sha256:', digest);
