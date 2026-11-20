'use strict';

/**
 * HOMI V1 tool catalog.
 * Loads the verified catalog (176 operations, 92 tools) and exposes only a
 * read-only projection. The catalog is data, never executable input.
 * Every canonical_service was validated against real module.exports.
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const CATALOG_PATH = path.join(__dirname, 'tool_catalog.json');
const raw = fs.readFileSync(CATALOG_PATH, 'utf8');
const catalog = JSON.parse(raw);
const digest = crypto.createHash('sha256').update(raw).digest('hex');

const TOOLS = new Map(catalog.tools.map((tool) => [tool.tool_id, Object.freeze(tool)]));

// Operearion registry derivada del catálogo: tools con risk != R0_READ son
// OPERATION WRITE (nombre canónico); el riesgo R0_READ se trata como READ.
const OPERATIONS = Object.freeze(
  catalog.tools.map((tool) =>
    Object.freeze({
      operation_id: tool.tool_id,
      domain: tool.domain,
      risk_class: tool.risk_class,
      http: { method: tool.http.method, path: tool.http.path },
    })
  )
);

if (TOOLS.size !== catalog.summary.implemented_tools) {
  throw new Error('homi_catalog_inconsistent: tool count mismatch');
}
for (const tool of TOOLS.values()) {
  if (!tool.input_schema || !tool.http || !tool.http.path || !tool.canonical_service) {
    throw new Error(`homi_catalog_invalid: ${tool.tool_id}`);
  }
}

function getTool(toolId) {
  return TOOLS.get(toolId) || null;
}

function allTools() {
  return Array.from(TOOLS.values());
}

function projectForModel(tool) {
  return Object.freeze({
    tool_id: tool.tool_id,
    description: tool.description,
    input_schema: tool.input_schema,
  });
}

function catalogDigest() {
  return digest;
}

function catalogSummary() {
  return Object.freeze({ ...catalog.summary, digest });
}

module.exports = {
  getTool,
  allTools,
  projectForModel,
  catalogDigest,
  catalogSummary,
  OPERATIONS,
};
