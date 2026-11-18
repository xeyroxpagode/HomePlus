/* Runtime proof for the dedicated QA household only. It uses a normal
 * authenticated QA member for every negative client-security check and every
 * Planner/message mutation. The local admin credential is read solely for
 * fixture-scoped inspection. No values are logged. */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const root = path.resolve(__dirname, '../..');
const workspaceDependency = (name) => {
  for (const searchPath of [path.join(root, 'node_modules'), path.join(root, 'backend', 'node_modules')]) {
    try { return require(require.resolve(name, { paths: [searchPath] })); } catch {}
  }
  throw new Error(`Missing QA runtime dependency: ${name}`);
};
const dotenv = workspaceDependency('dotenv');
const { createClient } = workspaceDependency('@supabase/supabase-js');
dotenv.config({ path: path.resolve(__dirname, '../../.env.qa') });
const { hashIdempotencyRequestV2 } = require('../../backend/src/lib/plannerIdempotencyAdapter');

const envValue = (lines, key) => (lines.find((line) => line.startsWith(`${key}=`)) || '').slice(key.length + 1).trim().replace(/^['"]|['"]$/g, '');
const frontEnv = fs.readFileSync(path.resolve(__dirname, '../../front/mi-front-limpio/.env'), 'utf8').split(/\r?\n/);
const url = process.env.QA_SUPABASE_URL;
const adminKey = process.env.QA_SUPABASE_SECRET_KEY || process.env.QA_SUPABASE_SERVICE_ROLE_KEY;
const anonKey = envValue(frontEnv, 'EXPO_PUBLIC_SUPABASE_ANON_KEY');
if (!url || !adminKey || !anonKey || !process.env.QA_A_EMAIL || !process.env.QA_A_PASSWORD || !process.env.QA_B_EMAIL || !process.env.QA_B_PASSWORD) throw new Error('QA runtime configuration is incomplete.');

const admin = createClient(url, adminKey, { auth: { persistSession: false, autoRefreshToken: false } });
const signIn = async (email, password) => {
  const client = createClient(url, anonKey, { auth: { persistSession: false, autoRefreshToken: false } });
  const { data, error } = await client.auth.signInWithPassword({ email, password });
  if (error || !data.session) throw new Error('QA user authentication failed.');
  return { client, userId: data.user.id };
};
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const uuid = () => crypto.randomUUID();
const mutation = async (client, householdId, task) => {
  const mutationId = `qa.mh1.${uuid()}`;
  const payload = {};
  const operation = 'planner.tasks.complete';
  const args = {
    p_household_id: householdId, p_task_id: task.id, p_action: 'complete', p_expected_version: task.version,
    p_payload: payload, p_request_id: `qa-${uuid()}`, p_mutation_id: mutationId,
    p_idempotency_key: `qa-${uuid()}`, p_operation: operation,
    p_payload_hash: hashIdempotencyRequestV2({ operation, scopeType: 'household', scopeId: householdId, targetId: task.id, payload, expectedVersion: task.version, mutationId }),
  };
  const { data, error } = await client.rpc('mutate_planner_task_v0', args);
  if (error) throw new Error(`Planner canonical completion failed: ${error.code || 'unknown'}`);
  return { data, args };
};

async function main() {
  const a = await signIn(process.env.QA_A_EMAIL, process.env.QA_A_PASSWORD);
  const b = await signIn(process.env.QA_B_EMAIL, process.env.QA_B_PASSWORD);
  const { data: person, error: personError } = await admin.from('people').select('id, active_household_id').eq('auth_user_id', a.userId).single();
  if (personError || !person?.active_household_id) throw new Error('QA household was not resolved.');
  const householdId = person.active_household_id;
  const { data: membership, error: memberError } = await admin.from('household_members').select('id').eq('household_id', householdId).eq('person_id', person.id).single();
  if (memberError || !membership) throw new Error('QA membership was not resolved.');

  // Runtime schema and executable trigger/RPC verification.
  for (const table of ['hplus_ledger_entries', 'messaging_message_reactions']) {
    const { error } = await admin.from(table).select('*', { head: true, count: 'exact' }).limit(1);
    if (error) throw new Error(`Runtime table missing: ${table}`);
  }
  const { error: summaryRpcError } = await a.client.rpc('hplus_get_summary', { p_household_id: householdId });
  if (summaryRpcError) throw new Error('H+ runtime summary function is unavailable.');

  const { data: tasks, error: tasksError } = await admin.from('planner_tasks')
    .select('id, title, version, estimated_duration_minutes, status').eq('household_id', householdId).like('title', 'QA E2E · tarea %').eq('status', 'pending');
  if (tasksError || !tasks || tasks.length < 3) throw new Error('Deterministic H+ QA tasks are missing.');
  const expected = new Map([[15, 5], [60, 10], [90, 20]]);
  const policyTasks = tasks.filter((task) => expected.has(task.estimated_duration_minutes));
  assert(policyTasks.length === 3, 'Expected 5/10/20 QA task tiers.');

  const ledgerBefore = await admin.from('hplus_ledger_entries').select('id').eq('household_id', householdId);
  if (ledgerBefore.error) throw new Error('Ledger read failed.');
  const realtimeEvents = [];
  await a.client.realtime.setAuth((await a.client.auth.getSession()).data.session.access_token);
  const hplusChannel = a.client.channel(`qa-hplus-runtime-${uuid()}`)
    .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'hplus_ledger_entries', filter: `household_id=eq.${householdId}` }, (payload) => realtimeEvents.push(payload.new))
    .subscribe();
  await new Promise((resolve) => setTimeout(resolve, 800));

  const completed = [];
  for (const task of policyTasks) {
    const { data } = await mutation(a.client, householdId, task);
    assert(['updated', 'noop', 'replay'].includes(data?.outcome), 'Canonical Planner outcome invalid.');
    const { data: entries, error } = await admin.from('hplus_ledger_entries').select('*')
      .eq('household_id', householdId).eq('event_type', 'task_completed').eq('source_type', 'planner_task').eq('source_id', task.id);
    if (error || entries?.length !== 1) throw new Error('Exactly-once ledger persistence failed.');
    const entry = entries[0];
    assert(entry.membership_id === membership.id && entry.points === expected.get(task.estimated_duration_minutes), 'Ledger attribution or policy points invalid.');
    assert(entry.idempotency_key === `task_completed:${task.id}`, 'Ledger idempotency key invalid.');
    completed.push({ task, entry });
  }
  await new Promise((resolve) => setTimeout(resolve, 1200));
  await a.client.removeChannel(hplusChannel);
  assert(realtimeEvents.length >= 1, 'H+ realtime INSERT was not received.');

  // Replaying a terminal Planner operation cannot create another source entry.
  const first = completed[0];
  const { data: reloadedTask } = await admin.from('planner_tasks').select('id, version, status').eq('id', first.task.id).single();
  await mutation(a.client, householdId, reloadedTask);
  const { count: replayCount, error: replayError } = await admin.from('hplus_ledger_entries').select('id', { count: 'exact', head: true }).eq('source_id', first.task.id).eq('event_type', 'task_completed');
  if (replayError || replayCount !== 1) throw new Error('Replay created a duplicate H+ award.');

  const { data: allLedger, error: allLedgerError } = await admin.from('hplus_ledger_entries').select('*').eq('household_id', householdId);
  if (allLedgerError) throw new Error('Ledger verification read failed.');
  const myExpected = allLedger.filter((entry) => entry.membership_id === membership.id).reduce((sum, entry) => sum + Number(entry.points), 0);
  const householdExpected = allLedger.reduce((sum, entry) => sum + Number(entry.points), 0);
  const { data: summary, error: summaryError } = await a.client.rpc('hplus_get_summary', { p_household_id: householdId }).single();
  if (summaryError || Number(summary.my_points) !== myExpected || Number(summary.household_points) !== householdExpected) throw new Error('Derived H+ summary mismatch.');

  // Negative checks use normal user authority, never admin.
  const spoof = { household_id: householdId, membership_id: membership.id, event_type: 'task_completed', source_type: 'planner_task', source_id: first.task.id, points: 20, occurred_at: new Date().toISOString(), idempotency_key: `spoof:${uuid()}` };
  const insertAttempt = await a.client.from('hplus_ledger_entries').insert(spoof);
  const updateAttempt = await a.client.from('hplus_ledger_entries').update({ points: 20 }).eq('id', first.entry.id);
  const deleteAttempt = await a.client.from('hplus_ledger_entries').delete().eq('id', first.entry.id);
  assert(insertAttempt.error && updateAttempt.error && deleteAttempt.error, 'Normal client mutated immutable ledger.');

  const { data: conversation, error: conversationError } = await admin.from('messaging_conversations').select('id').eq('household_id', householdId).eq('conversation_type', 'household').single();
  if (conversationError || !conversation) throw new Error('QA household conversation missing.');
  const { data: message, error: messageError } = await a.client.rpc('messaging_send_text_message', { p_conversation_id: conversation.id, p_body: `qa mh1 ${uuid()}`, p_client_message_id: uuid() });
  if (messageError || !message) throw new Error('Message runtime send failed.');
  const reactionEvents = [];
  const reactionChannel = a.client.channel(`qa-reaction-runtime-${uuid()}`)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'messaging_message_reactions' }, (payload) => reactionEvents.push(payload))
    .subscribe();
  await new Promise((resolve) => setTimeout(resolve, 800));
  for (const reactionType of ['like', 'thanks', 'thanks']) {
    const { error } = await a.client.rpc('messaging_toggle_reaction', { p_message_id: message.id, p_reaction_type: reactionType });
    if (error) throw new Error('Reaction runtime toggle failed.');
  }
  const { count: reactionCount, error: reactionError } = await admin.from('messaging_message_reactions').select('*', { count: 'exact', head: true }).eq('message_id', message.id);
  if (reactionError || reactionCount !== 0) throw new Error('Reaction add/change/remove did not converge to zero.');
  await new Promise((resolve) => setTimeout(resolve, 800));
  await a.client.removeChannel(reactionChannel);
  assert(reactionEvents.length >= 2, 'Reaction realtime changes were not received.');
  const { count: finalLedgerCount, error: finalLedgerError } = await admin.from('hplus_ledger_entries').select('*', { count: 'exact', head: true }).eq('household_id', householdId);
  if (finalLedgerError || finalLedgerCount !== allLedger.length) throw new Error('Message or reaction changed the H+ ledger.');

  // B sends after A's read cursor: only the remote message can be unread.
  const { data: bMessage, error: bMessageError } = await b.client.rpc('messaging_send_text_message', { p_conversation_id: conversation.id, p_body: `qa unread ${uuid()}`, p_client_message_id: uuid() });
  if (bMessageError || !bMessage) throw new Error('Incoming message check failed.');
  const { error: readError } = await a.client.rpc('messaging_mark_conversation_read', { p_conversation_id: conversation.id, p_through_sequence: Number(message.sequence) });
  if (readError) throw new Error('Read cursor mutation failed.');
  const { data: participant, error: participantError } = await admin.from('messaging_conversation_participants').select('last_read_sequence').eq('conversation_id', conversation.id).eq('membership_id', membership.id).single();
  assert(!participantError && Number(participant.last_read_sequence) === Number(message.sequence) && Number(bMessage.sequence) > Number(participant.last_read_sequence), 'Unread cursor lost incoming message.');
  console.log('M+H1 RUNTIME: PASS (schema, 5/10/20, exactly-once, security, summary, realtime, messages)');
}
main().catch((error) => { console.error(`M+H1 RUNTIME: FAIL ${error.message}`); process.exit(1); });
