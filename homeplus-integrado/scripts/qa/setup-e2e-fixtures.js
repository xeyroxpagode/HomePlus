#!/usr/bin/env node
'use strict';

/**
 * Safe, idempotent fixtures for device E2E only.
 *
 * This script never creates authentication accounts or changes passwords. It
 * only operates after an explicit QA opt-in and only on the dedicated
 * qa-maestro-homeplus household. The preferred Supabase secret key (or legacy
 * service-role credential) remains in the local/CI process environment and is
 * never available to the mobile app.
 */
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
function requireWorkspaceDependency(name) {
  const searchPaths = [
    path.join(root, 'node_modules'),
    path.join(root, 'backend', 'node_modules'),
  ];
  for (const searchPath of searchPaths) {
    try {
      return require(require.resolve(name, { paths: [searchPath] }));
    } catch {
      // Try the next workspace runtime. The production mobile bundle is never
      // involved in this development-only bootstrap.
    }
  }
  throw new Error(`Missing QA bootstrap dependency: ${name}`);
}
const dotenv = requireWorkspaceDependency('dotenv');
const { createClient } = requireWorkspaceDependency('@supabase/supabase-js');

const qaEnv = process.env.HOMEPLUS_QA_ENV_FILE || path.join(root, '.env.qa');
if (fs.existsSync(qaEnv)) dotenv.config({ path: qaEnv, override: false });

function decodeJwtRole(key) {
  const parts = String(key || '').split('.');
  if (parts.length !== 3) return null;
  try { return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')).role || null; } catch { return null; }
}
function resolveAdminCredential() {
  if (/^sb_secret_[A-Za-z0-9_-]+$/.test(String(process.env.QA_SUPABASE_SECRET_KEY || ''))) return process.env.QA_SUPABASE_SECRET_KEY;
  if (/^sb_secret_[A-Za-z0-9_-]+$/.test(String(process.env.QA_SUPABASE_SERVICE_ROLE_KEY || ''))) return process.env.QA_SUPABASE_SERVICE_ROLE_KEY;
  if (decodeJwtRole(process.env.QA_SUPABASE_SERVICE_ROLE_KEY) === 'service_role') return process.env.QA_SUPABASE_SERVICE_ROLE_KEY;
  return null;
}

const required = [
  'QA_FIXTURES_ENABLED',
  'QA_ENVIRONMENT',
  'QA_SUPABASE_URL',
  'QA_A_EMAIL',
  'QA_B_EMAIL',
  'QA_C_EMAIL',
];
const missing = required.filter((key) => !process.env[key]);
if (missing.length) {
  console.error(`[QA fixtures] Missing configuration: ${missing.join(', ')}`);
  process.exit(1);
}
if (process.env.QA_FIXTURES_ENABLED !== 'true') {
  console.error('[QA fixtures] Refusing to write: QA_FIXTURES_ENABLED must be true.');
  process.exit(1);
}
if (!['qa', 'development', 'dev'].includes(process.env.QA_ENVIRONMENT.toLowerCase())) {
  console.error('[QA fixtures] Refusing to write outside QA/development.');
  process.exit(1);
}
const adminCredential = resolveAdminCredential();
if (!adminCredential) {
  console.error('[QA fixtures] Missing valid QA_SUPABASE_SECRET_KEY or legacy QA_SUPABASE_SERVICE_ROLE_KEY.');
  process.exit(1);
}

const admin = createClient(
  process.env.QA_SUPABASE_URL,
  adminCredential,
  { auth: { persistSession: false, autoRefreshToken: false } },
);

const HOUSEHOLD_SLUG = 'qa-maestro-homeplus';
const HOUSEHOLD_NAME = 'QA Maestro HomePlus';
const users = [
  { key: 'A', email: process.env.QA_A_EMAIL.trim().toLowerCase(), role: 'coordinator', displayName: 'QA Coordinator' },
  { key: 'B', email: process.env.QA_B_EMAIL.trim().toLowerCase(), role: 'adult', displayName: 'QA Member B' },
  { key: 'C', email: process.env.QA_C_EMAIL.trim().toLowerCase(), role: 'adult', displayName: 'QA Member C' },
];

function fail(error, context) {
  if (!error) return;
  throw new Error(`${context}: ${error.message}`);
}

async function findAuthUser(email) {
  let page = 1;
  while (true) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
    fail(error, 'Unable to inspect QA auth accounts');
    const found = data.users.find((user) => user.email?.toLowerCase() === email);
    if (found) return found;
    if (data.users.length < 1000) break;
    page += 1;
  }
  throw new Error('A required QA account does not exist. Create the dedicated account through the approved QA process; this script never creates accounts or passwords.');
}

async function ensurePerson(authUser, fixture) {
  const { data: existing, error: lookupError } = await admin
    .from('people')
    .select('id')
    .eq('auth_user_id', authUser.id)
    .maybeSingle();
  fail(lookupError, 'Unable to read QA person');
  if (existing) return existing;

  const { data, error } = await admin
    .from('people')
    .insert({
      auth_user_id: authUser.id,
      display_name: fixture.displayName,
      default_language: 'es-419',
      personal_settings: {},
      app_onboarding_status: 'completed',
      app_onboarding_completed_at: new Date().toISOString(),
    })
    .select('id')
    .single();
  fail(error, 'Unable to create the projection for an existing QA account');
  return data;
}

async function ensureHousehold(coordinatorPersonId) {
  const { data: existing, error: lookupError } = await admin
    .from('households')
    .select('id')
    .eq('slug', HOUSEHOLD_SLUG)
    .maybeSingle();
  fail(lookupError, 'Unable to read QA household');
  if (existing) return existing;

  const { data, error } = await admin
    .from('households')
    .insert({
      name: HOUSEHOLD_NAME,
      slug: HOUSEHOLD_SLUG,
      timezone: 'America/Montevideo',
      default_language: 'es-419',
      config: { qa_fixture: true },
      created_by_person_id: coordinatorPersonId,
    })
    .select('id')
    .single();
  fail(error, 'Unable to create QA household');
  return data;
}

async function ensureMembership(householdId, personId, role) {
  const { data: existing, error: lookupError } = await admin
    .from('household_members')
    .select('id')
    .eq('household_id', householdId)
    .eq('person_id', personId)
    .maybeSingle();
  fail(lookupError, 'Unable to read QA membership');

  const values = {
    role,
    status: 'active',
    joined_at: new Date().toISOString(),
    left_at: null,
    household_onboarding_status: 'completed',
    household_onboarding_completed_at: new Date().toISOString(),
  };
  if (existing) {
    const { error } = await admin.from('household_members').update(values).eq('id', existing.id);
    fail(error, 'Unable to refresh QA membership');
    return { id: existing.id, person_id: personId };
  }
  const { data, error } = await admin
    .from('household_members')
    .insert({ household_id: householdId, person_id: personId, ...values })
    .select('id, person_id')
    .single();
  fail(error, 'Unable to create QA membership');
  return data;
}

async function resetQaHouseholdData(householdId) {
  // H+ history is intentionally immutable, including for QA fixture resets.
  // New fixture task IDs make each run independently awardable without
  // rewriting past contributions or touching any non-QA household.
  const { data: conversations, error: conversationsError } = await admin
    .from('messaging_conversations')
    .select('id')
    .eq('household_id', householdId);
  fail(conversationsError, 'Unable to read QA conversations');
  const ids = (conversations ?? []).map((row) => row.id);
  if (ids.length) {
    const { error: messageError } = await admin.from('messaging_messages').delete().in('conversation_id', ids);
    fail(messageError, 'Unable to reset QA messages');
    const { error: participantError } = await admin.from('messaging_conversation_participants').delete().in('conversation_id', ids);
    fail(participantError, 'Unable to reset QA conversation participants');
  }
  const { error: conversationError } = await admin.from('messaging_conversations').delete().eq('household_id', householdId);
  fail(conversationError, 'Unable to reset QA conversations');

  // Tasks are scoped to the dedicated household. Planner's database triggers
  // clean their canonical assignment/fulfillment rows through FK cascades.
  const { error: taskError } = await admin.from('planner_tasks').delete().eq('household_id', householdId);
  fail(taskError, 'Unable to reset QA tasks');
}

async function seedConversation(householdId, memberships) {
  const { data: conversation, error } = await admin
    .from('messaging_conversations')
    .insert({ household_id: householdId, conversation_type: 'household' })
    .select('id')
    .single();
  fail(error, 'Unable to create QA household conversation');
  const { error: participantError } = await admin
    .from('messaging_conversation_participants')
    .insert(memberships.map((membership) => ({ conversation_id: conversation.id, membership_id: membership.id })));
  fail(participantError, 'Unable to seed QA conversation participants');
}

async function seedPendingTask(householdId, coordinatorPersonId, coordinatorMembershipId) {
  const dueDate = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const base = {
    household_id: householdId,
    description: 'Fixture aislado para Mensajes, Planner y H+.',
    status: 'pending', priority: 'normal', due_date: dueDate,
    requires_verification: false, created_by_person_id: coordinatorPersonId,
    created_by_member_id: coordinatorMembershipId, assigned_to_member_id: null,
  };
  const { error } = await admin.from('planner_tasks').insert([
    { ...base, title: 'QA E2E · tarea corta', estimated_duration_minutes: 15 },
    { ...base, title: 'QA E2E · tarea media', estimated_duration_minutes: 60 },
    { ...base, title: 'QA E2E · tarea larga', estimated_duration_minutes: 90 },
  ]);
  fail(error, 'Unable to create QA deterministic H+ tasks');
}

async function main() {
  const authUsers = await Promise.all(users.map((fixture) => findAuthUser(fixture.email)));
  const people = await Promise.all(authUsers.map((authUser, index) => ensurePerson(authUser, users[index])));
  const household = await ensureHousehold(people[0].id);
  const memberships = [];
  for (let index = 0; index < people.length; index += 1) {
    memberships.push(await ensureMembership(household.id, people[index].id, users[index].role));
    const { error } = await admin
      .from('people')
      .update({
        active_household_id: household.id,
        app_onboarding_status: 'completed',
        app_onboarding_completed_at: new Date().toISOString(),
      })
      .eq('id', people[index].id);
    fail(error, 'Unable to activate QA household for account');
  }

  await resetQaHouseholdData(household.id);
  await seedConversation(household.id, memberships);
  await seedPendingTask(household.id, people[0].id, memberships[0].id);
  console.log('[QA fixtures] READY: dedicated household, A/B/C memberships, household conversation, and 5/10/20 unassigned tasks.');
}

main().catch((error) => {
  console.error(`[QA fixtures] FAILED: ${error.message}`);
  process.exit(1);
});
