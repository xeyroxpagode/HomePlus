#!/usr/bin/env node
'use strict';

/* Runtime proof for M2 against the dedicated QA household only. The mobile
 * app never receives the admin credential; it is used here solely to inspect
 * fixture-scoped persistence. API writes use ordinary authenticated users. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const resolveDependency = (name) => require(require.resolve(name, {
  paths: [path.join(root, 'node_modules'), path.join(root, 'backend', 'node_modules')],
}));
const dotenv = resolveDependency('dotenv');
const { createClient } = resolveDependency('@supabase/supabase-js');

dotenv.config({ path: path.join(root, '.env.qa') });
const frontEnv = fs.readFileSync(path.join(root, 'front/mi-front-limpio/.env'), 'utf8');
const env = (key) => ((frontEnv.match(new RegExp(`^${key}=(.*)$`, 'm')) || [])[1] || '').trim().replace(/^['"]|['"]$/g, '');
const url = process.env.QA_SUPABASE_URL;
const adminKey = process.env.QA_SUPABASE_SECRET_KEY || process.env.QA_SUPABASE_SERVICE_ROLE_KEY;
const anonKey = env('EXPO_PUBLIC_SUPABASE_ANON_KEY');
const api = 'http://127.0.0.1:3001/api';
if (![url, adminKey, anonKey, process.env.QA_A_EMAIL, process.env.QA_A_PASSWORD, process.env.QA_B_EMAIL, process.env.QA_B_PASSWORD, process.env.QA_C_EMAIL, process.env.QA_C_PASSWORD].every(Boolean)) {
  throw new Error('QA runtime configuration is incomplete.');
}

const admin = createClient(url, adminKey, { auth: { persistSession: false, autoRefreshToken: false } });
const uuid = () => crypto.randomUUID();
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const signIn = async (email, password) => {
  const client = createClient(url, anonKey, { auth: { persistSession: false, autoRefreshToken: false } });
  const { data, error } = await client.auth.signInWithPassword({ email, password });
  if (error || !data.session) throw new Error('QA user authentication failed.');
  return { client, token: data.session.access_token, userId: data.user.id };
};
const request = async (actor, method, pathname, body, extraHeaders = {}) => {
  const response = await fetch(`${api}${pathname}`, {
    method,
    headers: {
      Authorization: `Bearer ${actor.token}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...extraHeaders,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  let json = null;
  try { json = await response.json(); } catch {}
  return { status: response.status, body: json };
};
const media = {
  image: { mime: 'image/png', name: 'qa-image.png', bytes: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9J8QAAAABJRU5ErkJggg==', 'base64'), width: 1, height: 1 },
  audio: { mime: 'audio/mpeg', name: 'qa-audio.mp3', bytes: Buffer.from('ID3\x04\0\0\0\0\0\x15QA HomePlus audio runtime'), duration: 1200 },
  file: { mime: 'application/pdf', name: 'qa-file.pdf', bytes: Buffer.from('%PDF-1.4\n% QA HomePlus\n%%EOF\n') },
};

const registerUploadCommit = async (actor, conversationId, kind, { duplicate = true } = {}) => {
  const sample = media[kind];
  const attachmentId = uuid();
  const registration = await request(actor, 'POST', `/messages/conversations/${conversationId}/attachments`, {
    client_attachment_id: attachmentId, kind, mime_type: sample.mime, original_name: sample.name,
    size_bytes: sample.bytes.length, width: sample.width, height: sample.height, duration_ms: sample.duration,
  });
  assert(registration.status === 201 && registration.body?.attachment?.id, `${kind} attachment registration failed.`);
  const attachment = registration.body.attachment;
  const signed = await request(actor, 'POST', `/messages/attachments/${attachment.id}/upload`, {});
  assert(signed.status === 200 && signed.body?.signed_upload_url, `${kind} signed upload authorization failed.`);
  const upload = await fetch(signed.body.signed_upload_url, { method: 'PUT', headers: { 'Content-Type': sample.mime }, body: sample.bytes });
  assert(upload.ok, `${kind} private object upload failed.`);
  const verified = await request(actor, 'POST', `/messages/attachments/${attachment.id}/verify`, {});
  assert(verified.status === 200 && verified.body?.verified, `${kind} upload verification failed.`);
  const clientMessageId = uuid();
  const committed = await request(actor, 'POST', `/messages/conversations/${conversationId}/messages`, {
    type: kind, attachment_id: attachment.id, client_message_id: clientMessageId,
  });
  assert(committed.status === 201 && committed.body?.message?.id, `${kind} message commit failed.`);
  if (duplicate) {
    const replay = await request(actor, 'POST', `/messages/conversations/${conversationId}/messages`, {
      type: kind, attachment_id: attachment.id, client_message_id: clientMessageId,
    });
    assert(replay.status === 201 && replay.body?.message?.id === committed.body.message.id, `${kind} HTTP retry was not idempotent.`);
  }
  return { attachment: { ...attachment, id: attachment.id }, message: committed.body.message, bytes: sample.bytes };
};

async function main() {
  const a = await signIn(process.env.QA_A_EMAIL, process.env.QA_A_PASSWORD);
  const b = await signIn(process.env.QA_B_EMAIL, process.env.QA_B_PASSWORD);
  const c = await signIn(process.env.QA_C_EMAIL, process.env.QA_C_PASSWORD);
  const { data: person, error: personError } = await admin.from('people').select('id, active_household_id').eq('auth_user_id', a.userId).single();
  if (personError || !person?.active_household_id) throw new Error('QA household was not resolved.');
  const householdId = person.active_household_id;
  const { data: membership } = await admin.from('household_members').select('id').eq('household_id', householdId).eq('person_id', person.id).single();
  assert(membership?.id, 'QA membership was not resolved.');
  const { data: conversation } = await admin.from('messaging_conversations').select('id').eq('household_id', householdId).eq('conversation_type', 'household').single();
  assert(conversation?.id, 'QA household conversation is missing.');

  // Schema, private bucket and executable data-plane checks.
  for (const table of ['messaging_attachments', 'messaging_message_actions']) {
    const { error } = await admin.from(table).select('id', { head: true }).limit(1);
    assert(!error, `Runtime table ${table} is unavailable.`);
  }
  const { data: bucket, error: bucketError } = await admin.storage.getBucket('messaging-attachments');
  assert(!bucketError && bucket && bucket.public === false && Number(bucket.file_size_limit) === 50 * 1024 * 1024, 'Messaging Storage bucket is not private or has an invalid limit.');

  const ledgerBefore = await admin.from('hplus_ledger_entries').select('id', { count: 'exact', head: true }).eq('household_id', householdId);
  assert(!ledgerBefore.error, 'Unable to establish H+ ledger baseline.');
  const events = { messages: [], attachments: [] };
  await a.client.realtime.setAuth(a.token);
  const channel = a.client.channel(`qa-m2-media-${uuid()}`)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'messaging_messages', filter: `conversation_id=eq.${conversation.id}` }, (payload) => events.messages.push(payload))
    .on('postgres_changes', { event: '*', schema: 'public', table: 'messaging_attachments', filter: `conversation_id=eq.${conversation.id}` }, (payload) => events.attachments.push(payload))
    .subscribe();
  await pause(900);

  // Safe failed-upload recovery: verify before object exists, then continue the
  // same logical attachment identity rather than creating another message.
  const retryId = uuid();
  const retryRegistration = await request(a, 'POST', `/messages/conversations/${conversation.id}/attachments`, {
    client_attachment_id: retryId, kind: 'image', mime_type: media.image.mime, original_name: 'qa-retry.png', size_bytes: media.image.bytes.length, width: 1, height: 1,
  });
  assert(retryRegistration.status === 201, `Retry attachment registration failed (HTTP ${retryRegistration.status}).`);
  const missingVerify = await request(a, 'POST', `/messages/attachments/${retryRegistration.body.attachment.id}/verify`, {});
  assert(missingVerify.status === 409, 'Missing upload did not remain recoverable.');
  const retryUpload = await request(a, 'POST', `/messages/attachments/${retryRegistration.body.attachment.id}/upload`, {});
  const retryPut = await fetch(retryUpload.body.signed_upload_url, { method: 'PUT', headers: { 'Content-Type': media.image.mime }, body: media.image.bytes });
  assert(retryPut.ok, 'Retry object upload failed.');
  const retryVerify = await request(a, 'POST', `/messages/attachments/${retryRegistration.body.attachment.id}/verify`, {});
  assert(retryVerify.status === 200, 'Retry verification failed.');
  const retryMessageId = uuid();
  const retryCommit = await request(a, 'POST', `/messages/conversations/${conversation.id}/messages`, { type: 'image', attachment_id: retryRegistration.body.attachment.id, client_message_id: retryMessageId });
  const retryReplay = await request(a, 'POST', `/messages/conversations/${conversation.id}/messages`, { type: 'image', attachment_id: retryRegistration.body.attachment.id, client_message_id: retryMessageId });
  assert(retryCommit.status === 201 && retryReplay.body?.message?.id === retryCommit.body?.message?.id, 'Retry generated duplicate image message.');

  const image = await registerUploadCommit(a, conversation.id, 'image');
  const audio = await registerUploadCommit(a, conversation.id, 'audio');
  const file = await registerUploadCommit(a, conversation.id, 'file');
  await pause(1200);
  await a.client.removeChannel(channel);
  assert(events.messages.length >= 4 && events.attachments.length >= 4, 'Realtime did not emit canonical media changes.');

  for (const item of [image, audio, file]) {
    const { count, error } = await admin.from('messaging_messages').select('id', { count: 'exact', head: true }).eq('id', item.message.id);
    assert(!error && count === 1, `${item.message.type} created duplicate DB messages.`);
    const { count: attachmentCount, error: attachmentError } = await admin.from('messaging_attachments').select('id', { count: 'exact', head: true }).eq('id', item.attachment.id).eq('message_id', item.message.id).eq('lifecycle', 'committed');
    assert(!attachmentError && attachmentCount === 1, `${item.message.type} created duplicate or uncommitted attachments.`);
    const download = await request(b, 'GET', `/messages/attachments/${item.attachment.id}/download`);
    assert(download.status === 200 && download.body?.signed_url && !download.body.signed_url.includes('/public/'), `${item.message.type} authorized private download failed.`);
    const read = await fetch(download.body.signed_url);
    assert(read.ok, `${item.message.type} signed read failed.`);
  }

  // Reactions remain generic across media and never award H+.
  const reactionStates = [];
  for (const type of ['like', 'thanks', 'thanks']) {
    const reaction = await request(a, 'POST', `/messages/${image.message.id}/reaction`, { reaction_type: type });
    assert(reaction.status === 200, `Media reaction mutation failed (HTTP ${reaction.status}, ${reaction.body?.error?.code || reaction.body?.code || 'no_code'}).`);
    reactionStates.push(reaction.body?.state);
  }
  const { count: noReaction, error: reactionCountError } = await admin.from('messaging_message_reactions').select('message_id', { count: 'exact', head: true }).eq('message_id', image.message.id);
  assert(!reactionCountError && noReaction === 0, `Media reaction add/change/remove did not converge (${reactionStates.join(',')}; ${noReaction ?? 'unknown'}).`);

  // Read cursor: A reads through its own media; B then sends media, which is
  // the only unread item. A self-send must not add unread.
  const latestASequence = Math.max(image.message.sequence, audio.message.sequence, file.message.sequence, retryCommit.body.message.sequence);
  const marked = await request(a, 'POST', `/messages/conversations/${conversation.id}/read`, { through_sequence: latestASequence });
  assert(marked.status === 200, 'Media read cursor update failed.');
  const remote = await registerUploadCommit(b, conversation.id, 'image');
  const inboxUnread = await request(a, 'GET', '/messages/conversations');
  const householdRow = inboxUnread.body?.conversations?.find((row) => row.id === conversation.id);
  assert(inboxUnread.status === 200 && Number(householdRow?.read_state?.unread_count) >= 1, 'Remote media did not increment unread.');
  const markedRemote = await request(a, 'POST', `/messages/conversations/${conversation.id}/read`, { through_sequence: remote.message.sequence });
  assert(markedRemote.status === 200, 'Remote media read failed.');
  const self = await registerUploadCommit(a, conversation.id, 'file');
  const selfInbox = await request(a, 'GET', '/messages/conversations');
  const selfRow = selfInbox.body?.conversations?.find((row) => row.id === conversation.id);
  assert(Number(selfRow?.read_state?.unread_count) === 0, 'Self media inflated unread.');

  // Text -> canonical Planner task -> non-authoritative source linkage.
  const text = await request(a, 'POST', `/messages/conversations/${conversation.id}/messages`, { body: `QA M2 action ${uuid()}`, client_message_id: uuid() });
  assert(text.status === 201 && text.body?.message?.id, 'Text source message creation failed.');
  const taskHeaders = { 'X-Mutation-Id': `qa-m2-${uuid()}`, 'Idempotency-Key': `qa-m2-${uuid()}` };
  const taskCreate = await request(a, 'POST', '/planner/tasks', { title: `QA M2 tarea ${uuid()}`, description: text.body.message.body, priority: 'normal', requires_verification: false }, taskHeaders);
  assert(taskCreate.status === 201 && taskCreate.body?.task?.id, 'Canonical Planner task creation failed.');
  const taskId = taskCreate.body.task.id;
  const link = await request(a, 'POST', `/messages/${text.body.message.id}/actions/task`, { task_id: taskId });
  assert(link.status === 201 && link.body?.action?.entity_id === taskId, 'Message-to-Task source linkage failed.');
  const { data: action } = await admin.from('messaging_message_actions').select('message_id, entity_id, action_type').eq('message_id', text.body.message.id).single();
  assert(action?.entity_id === taskId && action.action_type === 'task', 'Source linkage is not persisted canonically.');
  const { data: plannerTask } = await admin.from('planner_tasks').select('id, household_id').eq('id', taskId).single();
  assert(plannerTask?.household_id === householdId, 'Planner did not remain task authority.');

  // Orphan cleanup is narrowly scoped: a wrong sender cannot commit an A
  // upload, then A cancels exactly that staging object.
  const orphan = await request(a, 'POST', `/messages/conversations/${conversation.id}/attachments`, { client_attachment_id: uuid(), kind: 'file', mime_type: media.file.mime, original_name: 'qa-orphan.pdf', size_bytes: media.file.bytes.length });
  assert(orphan.status === 201, 'Orphan fixture registration failed.');
  const orphanUpload = await request(a, 'POST', `/messages/attachments/${orphan.body.attachment.id}/upload`, {});
  assert((await fetch(orphanUpload.body.signed_upload_url, { method: 'PUT', headers: { 'Content-Type': media.file.mime }, body: media.file.bytes })).ok, 'Orphan upload failed.');
  assert((await request(a, 'POST', `/messages/attachments/${orphan.body.attachment.id}/verify`, {})).status === 200, 'Orphan verify failed.');
  const foreignCommit = await request(b, 'POST', `/messages/conversations/${conversation.id}/messages`, { type: 'file', attachment_id: orphan.body.attachment.id, client_message_id: uuid() });
  assert(foreignCommit.status >= 400, 'Another member committed an attachment it did not create.');
  // Age this QA-only staging object and invoke the real server-only cleanup
  // command. It must remove this object/row without touching committed media.
  const agedAt = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString();
  const aged = await admin.from('messaging_attachments').update({ created_at: agedAt }).eq('id', orphan.body.attachment.id);
  assert(!aged.error, 'Unable to age QA staging attachment for cleanup validation.');
  const cleanup = spawnSync(process.execPath, ['scripts/cleanup-messaging-attachments.js'], {
    cwd: path.join(root, 'backend'),
    env: { ...process.env, SUPABASE_SERVICE_ROLE_KEY: adminKey },
    encoding: 'utf8',
    timeout: 30000,
  });
  assert(cleanup.status === 0, `Expired staging cleanup command failed (exit ${cleanup.status ?? 'unknown'}).`);
  const { data: cleanedOrphan } = await admin.from('messaging_attachments').select('id').eq('id', orphan.body.attachment.id).maybeSingle();
  assert(!cleanedOrphan, 'Expired staging attachment was not cleaned.');

  // Runtime negative checks with normal user authority (not admin).
  const badMime = await request(a, 'POST', `/messages/conversations/${conversation.id}/attachments`, { client_attachment_id: uuid(), kind: 'file', mime_type: 'application/x-msdownload', original_name: 'unsafe.exe', size_bytes: 10 });
  const tooLarge = await request(a, 'POST', `/messages/conversations/${conversation.id}/attachments`, { client_attachment_id: uuid(), kind: 'file', mime_type: media.file.mime, original_name: 'large.pdf', size_bytes: 50 * 1024 * 1024 + 1 });
  assert(badMime.status === 400 && tooLarge.status === 400, 'MIME or 50 MB limit validation failed.');
  const directInsert = await a.client.from('messaging_attachments').insert({ id: uuid(), household_id: householdId, conversation_id: conversation.id, created_by_membership_id: membership.id, client_attachment_id: uuid(), attachment_kind: 'file', mime_type: media.file.mime, original_name: 'spoof.pdf', size_bytes: 4, storage_bucket: 'messaging-attachments', storage_path: `${householdId}/messages/${conversation.id}/${uuid()}` });
  const directUpdate = await a.client.from('messaging_attachments').update({ original_name: 'spoofed.pdf' }).eq('id', image.attachment.id);
  const directDelete = await a.client.from('messaging_attachments').delete().eq('id', image.attachment.id);
  assert(directInsert.error && directUpdate.error && directDelete.error, 'Normal client bypassed attachment write policy.');
  const crossConversation = await request(a, 'POST', '/messages/directs/ensure', { other_membership_id: (await admin.from('household_members').select('id').eq('household_id', householdId).neq('id', membership.id).limit(1)).data?.[0]?.id });
  assert(crossConversation.status === 200, 'Direct conversation setup failed.');
  const wrongConversation = await request(a, 'POST', `/messages/conversations/${crossConversation.body?.conversation?.id}/messages`, { type: 'image', attachment_id: image.attachment.id, client_message_id: uuid() });
  assert(wrongConversation.status >= 400, 'Cross-conversation attachment association was allowed.');

  // C is temporarily placed in an isolated QA household to prove that the
  // server derives the household from context and rejects A's attachment both
  // for read and upload. The active household is restored in all cases.
  const { data: personC } = await admin.from('people').select('id, active_household_id').eq('auth_user_id', c.userId).single();
  assert(personC?.id, 'QA C person was not resolved.');
  const isolatedSlug = `qa-m2-isolated-${uuid().slice(0, 8)}`;
  const { data: isolated, error: isolatedError } = await admin.from('households').insert({
    name: 'QA M2 Isolated', slug: isolatedSlug, timezone: 'America/Montevideo', default_language: 'es-419', config: { qa_fixture: true }, created_by_person_id: personC.id,
  }).select('id').single();
  assert(!isolatedError && isolated?.id, 'Unable to create isolated QA household.');
  try {
    const join = await admin.from('household_members').insert({ household_id: isolated.id, person_id: personC.id, role: 'adult', status: 'active', joined_at: new Date().toISOString(), household_onboarding_status: 'completed', household_onboarding_completed_at: new Date().toISOString() });
    assert(!join.error, 'Unable to join QA C to isolated household.');
    const activate = await admin.from('people').update({ active_household_id: isolated.id }).eq('id', personC.id);
    assert(!activate.error, 'Unable to activate isolated QA household.');
    const crossRead = await request(c, 'GET', `/messages/attachments/${image.attachment.id}/download`);
    const crossUpload = await request(c, 'POST', `/messages/conversations/${conversation.id}/attachments`, { client_attachment_id: uuid(), kind: 'file', mime_type: media.file.mime, original_name: 'cross.pdf', size_bytes: media.file.bytes.length });
    assert(crossRead.status >= 400 && crossUpload.status >= 400, 'Cross-household attachment access was allowed.');
  } finally {
    await admin.from('people').update({ active_household_id: householdId }).eq('id', personC.id);
    await admin.from('households').delete().eq('id', isolated.id);
  }

  const ledgerAfter = await admin.from('hplus_ledger_entries').select('id', { count: 'exact', head: true }).eq('household_id', householdId);
  assert(!ledgerAfter.error && ledgerAfter.count === ledgerBefore.count, 'Messaging/media/reaction/action mutated the H+ ledger.');
  console.log('M2 RUNTIME: PASS (schema, private storage, image/audio/file, lifecycle, realtime, unread, reactions, action, security, H+ zero delta)');
}

main().catch((error) => { console.error(`M2 RUNTIME: FAIL ${error.message}`); process.exit(1); });
