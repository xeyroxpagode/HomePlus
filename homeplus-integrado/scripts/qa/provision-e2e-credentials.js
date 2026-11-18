#!/usr/bin/env node
'use strict';

/**
 * Local/CI-only QA credential bootstrap.
 *
 * It never runs in the mobile app or as an HTTP endpoint.  A valid Supabase
 * Supabase secret key (preferred) or legacy service-role credential plus an
 * explicit QA/development opt-in are required
 * before it can create or update the three dedicated QA auth users.
 */
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const qaEnvPath = process.env.HOMEPLUS_QA_ENV_FILE || path.join(root, '.env.qa');

function requireWorkspaceDependency(name) {
  for (const searchPath of [path.join(root, 'node_modules'), path.join(root, 'backend', 'node_modules')]) {
    try {
      return require(require.resolve(name, { paths: [searchPath] }));
    } catch {
      // Continue with the workspace runtime that owns this dependency.
    }
  }
  throw new Error(`Missing QA bootstrap dependency: ${name}`);
}

const dotenv = requireWorkspaceDependency('dotenv');
const { createClient } = requireWorkspaceDependency('@supabase/supabase-js');

function readEnvFile(file) {
  if (!fs.existsSync(file)) return {};
  return dotenv.parse(fs.readFileSync(file));
}

function applyMissing(values) {
  for (const [key, value] of Object.entries(values)) {
    if (!process.env[key] && value) process.env[key] = value;
  }
}

function decodeJwtRole(key) {
  const parts = String(key || '').split('.');
  if (parts.length !== 3) return null;
  try {
    return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')).role || null;
  } catch {
    return null;
  }
}

function isLegacyServiceRole(key) {
  return decodeJwtRole(key) === 'service_role';
}

function isSupabaseSecretKey(key) {
  return /^sb_secret_[A-Za-z0-9_-]+$/.test(String(key || ''));
}

function resolveAdminCredential(secretKey, legacyServiceRoleKey) {
  if (isSupabaseSecretKey(secretKey)) return { key: secretKey, mode: 'secret' };
  // Existing local/CI deployments may still inject a current sb_secret key
  // under the legacy variable name. It is accepted only after the same strict
  // secret-key validation; anon and publishable keys remain invalid.
  if (isSupabaseSecretKey(legacyServiceRoleKey)) return { key: legacyServiceRoleKey, mode: 'secret_legacy_name' };
  if (isLegacyServiceRole(legacyServiceRoleKey)) return { key: legacyServiceRoleKey, mode: 'legacy_service_role' };
  return null;
}

function securePassword() {
  return `${crypto.randomBytes(32).toString('base64url')}Qa!7`;
}

function writeEnv(values) {
  const order = [
    'QA_FIXTURES_ENABLED', 'QA_ENVIRONMENT', 'QA_SUPABASE_URL', 'QA_SUPABASE_SECRET_KEY',
    'QA_SUPABASE_SERVICE_ROLE_KEY', 'QA_A_EMAIL', 'QA_A_PASSWORD',
    'QA_B_EMAIL', 'QA_B_PASSWORD', 'QA_C_EMAIL', 'QA_C_PASSWORD',
    'QA_INVALID_PASSWORD',
  ];
  const body = [
    '# Local/CI QA only. This file is ignored by Git.',
    '# Never copy either admin key into the mobile frontend.',
    ...order.map((key) => `${key}=${values[key] || ''}`),
    '',
  ].join('\n');
  fs.writeFileSync(qaEnvPath, body, { encoding: 'utf8', mode: 0o600 });
}

function buildLocalQaEnv() {
  const backend = readEnvFile(path.join(root, 'backend', '.env'));
  const frontend = readEnvFile(path.join(root, 'front', 'mi-front-limpio', '.env'));
  const existing = readEnvFile(qaEnvPath);
  const sourceSecretKey = existing.QA_SUPABASE_SECRET_KEY
    || process.env.QA_SUPABASE_SECRET_KEY
    || process.env.SUPABASE_SECRET_KEY
    || backend.SUPABASE_SECRET_KEY
    || '';
  const sourceServiceRole = existing.QA_SUPABASE_SERVICE_ROLE_KEY
    || process.env.QA_SUPABASE_SERVICE_ROLE_KEY
    || process.env.SUPABASE_SERVICE_ROLE_KEY
    || backend.SUPABASE_SERVICE_ROLE_KEY
    || backend.SUPABASE_SERVICE_KEY
    || backend.SUPABASE_KEY
    || '';
  const values = {
    QA_FIXTURES_ENABLED: existing.QA_FIXTURES_ENABLED || process.env.QA_FIXTURES_ENABLED || 'true',
    QA_ENVIRONMENT: existing.QA_ENVIRONMENT || process.env.QA_ENVIRONMENT || 'qa',
    QA_SUPABASE_URL: existing.QA_SUPABASE_URL || process.env.QA_SUPABASE_URL || process.env.SUPABASE_URL || backend.SUPABASE_URL || frontend.EXPO_PUBLIC_SUPABASE_URL || '',
    QA_SUPABASE_SECRET_KEY: sourceSecretKey,
    QA_SUPABASE_SERVICE_ROLE_KEY: sourceServiceRole,
    QA_A_EMAIL: existing.QA_A_EMAIL || process.env.QA_A_EMAIL || 'qa-a-maestro@homeplus.test',
    QA_A_PASSWORD: existing.QA_A_PASSWORD || process.env.QA_A_PASSWORD || '',
    QA_B_EMAIL: existing.QA_B_EMAIL || process.env.QA_B_EMAIL || 'qa-b-maestro@homeplus.test',
    QA_B_PASSWORD: existing.QA_B_PASSWORD || process.env.QA_B_PASSWORD || '',
    QA_C_EMAIL: existing.QA_C_EMAIL || process.env.QA_C_EMAIL || 'qa-c-maestro@homeplus.test',
    QA_C_PASSWORD: existing.QA_C_PASSWORD || process.env.QA_C_PASSWORD || '',
    QA_INVALID_PASSWORD: existing.QA_INVALID_PASSWORD || process.env.QA_INVALID_PASSWORD || '',
  };
  return { values, exists: fs.existsSync(qaEnvPath) };
}

async function findUser(admin, email) {
  for (let page = 1; ; page += 1) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
    if (error) throw new Error(`Unable to inspect QA auth users: ${error.message}`);
    const found = data.users.find((candidate) => candidate.email?.toLowerCase() === email.toLowerCase());
    if (found) return found;
    if (data.users.length < 1000) return null;
  }
}

async function ensureUser(admin, account) {
  const existing = await findUser(admin, account.email);
  if (existing) {
    if (account.passwordWasGenerated) {
      const { error } = await admin.auth.admin.updateUserById(existing.id, {
        password: account.password,
        email_confirm: true,
        user_metadata: { qa_fixture: true, qa_role: account.role },
      });
      if (error) throw new Error(`Unable to refresh dedicated QA account: ${error.message}`);
    }
    return;
  }
  const { error } = await admin.auth.admin.createUser({
    email: account.email,
    password: account.password,
    email_confirm: true,
    user_metadata: { qa_fixture: true, qa_role: account.role },
  });
  if (error) throw new Error(`Unable to create dedicated QA account: ${error.message}`);
}

async function main() {
  const { values, exists } = buildLocalQaEnv();
  applyMissing(values);

  // First invocation may safely create the ignored local template with only
  // derivable non-secrets. It does not create external users without admin key.
  if (!exists) writeEnv(values);

  if (values.QA_FIXTURES_ENABLED !== 'true' || !['qa', 'dev', 'development'].includes(values.QA_ENVIRONMENT.toLowerCase())) {
    throw new Error('Refusing QA credential provisioning outside an explicit QA/development environment.');
  }
  const adminCredential = resolveAdminCredential(values.QA_SUPABASE_SECRET_KEY, values.QA_SUPABASE_SERVICE_ROLE_KEY);
  if (!values.QA_SUPABASE_URL || !adminCredential) {
    throw new Error('A valid QA_SUPABASE_SECRET_KEY or legacy QA_SUPABASE_SERVICE_ROLE_KEY is required for local/CI QA provisioning; no users were changed.');
  }

  const generated = [];
  for (const key of ['QA_A_PASSWORD', 'QA_B_PASSWORD', 'QA_C_PASSWORD', 'QA_INVALID_PASSWORD']) {
    if (!values[key]) {
      values[key] = securePassword();
      generated.push(key);
    }
  }
  if (generated.length) writeEnv(values);
  applyMissing(values);

  const admin = createClient(values.QA_SUPABASE_URL, adminCredential.key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  await ensureUser(admin, { email: values.QA_A_EMAIL, password: values.QA_A_PASSWORD, passwordWasGenerated: generated.includes('QA_A_PASSWORD'), role: 'coordinator' });
  await ensureUser(admin, { email: values.QA_B_EMAIL, password: values.QA_B_PASSWORD, passwordWasGenerated: generated.includes('QA_B_PASSWORD'), role: 'member' });
  await ensureUser(admin, { email: values.QA_C_EMAIL, password: values.QA_C_PASSWORD, passwordWasGenerated: generated.includes('QA_C_PASSWORD'), role: 'member' });
  console.log('[QA credentials] READY: dedicated QA auth accounts are provisioned or reused.');
}

main().catch((error) => {
  console.error(`[QA credentials] FAILED: ${error.message}`);
  process.exit(1);
});
