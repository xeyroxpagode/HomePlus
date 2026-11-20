'use strict';

/**
 * HOMI V1 server-side authority.
 * Discovery and execution both re-derive capabilities from the authenticated
 * canonical HomePlus context. Hiding a tool is never a substitute for this.
 */
const { resolveCapabilities } = require('../../lib/plannerCapabilities');

const DENY = Object.freeze({ allowed: false, reason: 'authority_unavailable' });

function collectCapabilities(canonical) {
  const role = canonical && canonical.role;
  const membershipStatus = canonical && canonical.membershipStatus;
  const household = canonical && canonical.household;
  if (!role || !membershipStatus || !household) return DENY;

  let base;
  try {
    base = resolveCapabilities({ role, membershipStatus, household });
  } catch {
    return DENY;
  }
  if (!base || typeof base !== 'object') return DENY;

  const set = new Set(Object.keys(base).filter((key) => base[key] === true));

  // Domain capability resolvers are additive and fail-closed. The endpoint
  // itself remains the final authority for each mutation.
  const addons = [
    ['../../lib/inventoryCapabilities', 'resolveInventoryCapabilities'],
    ['../../lib/assetsCapabilities', 'resolveAssetsCapabilities'],
    ['../../lib/homecloudCapabilities', 'resolveHomeCloudCapabilities'],
    ['../../lib/householdPermissions', 'resolveHouseholdCapabilities'],
  ];
  for (const [modulePath, fn] of addons) {
    try {
      const mod = require(modulePath);
      if (typeof mod[fn] !== 'function') continue;
      const extra = mod[fn]({ role, membershipStatus, household });
      if (extra && typeof extra === 'object') {
        for (const key of Object.keys(extra)) if (extra[key] === true) set.add(key);
      }
    } catch {
      // Absent resolver simply contributes no capabilities.
    }
  }
  // Hierarchical capabilities implied by ownership.
  for (const key of Array.from(set)) {
    if (key === 'assets.manage') { set.add('assets.contribute'); set.add('assets.view'); }
    if (key === 'assets.contribute') set.add('assets.view');
    if (key === 'inventory.manage') { set.add('inventory.use'); set.add('inventory.view'); }
    if (key === 'inventory.use') set.add('inventory.view');
    if (key === 'homecloud.organize') { set.add('homecloud.contribute'); set.add('homecloud.view'); }
    if (key === 'homecloud.delete') { set.add('homecloud.contribute'); set.add('homecloud.view'); }
    if (key === 'homecloud.contribute') set.add('homecloud.view');
  }
  return Object.freeze({ allowed: true, set });
}

function isToolVisible(tool, canonical, context) {
  if (!tool || !context || !context.householdId) return false;
  const caps = collectCapabilities(canonical);
  if (!caps.allowed) return false;
  for (const required of tool.required_capabilities || []) {
    if (!caps.set.has(required)) return false;
  }
  // PERSONAL-scope-only tools require a resolved actor; HOUSEHOLD tools require
  // a household, already checked above.
  if (tool.household_scope === 'PERSONAL' && !context.actorId) return false;
  return true;
}

function assertExecutionAuthority(tool, canonical, context) {
  if (!isToolVisible(tool, canonical, context)) {
    const error = new Error('homi_forbidden_capability');
    error.code = 'homi_forbidden_capability';
    error.statusCode = 403;
    error.details = { tool_id: tool && tool.tool_id };
    throw error;
  }
}

module.exports = { collectCapabilities, isToolVisible, assertExecutionAuthority };

