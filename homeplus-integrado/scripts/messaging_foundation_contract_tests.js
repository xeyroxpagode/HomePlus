#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const expect = (condition, message) => {
  if (!condition) throw new Error(message);
};

try {
  const migration = read('supabase/migrations/202610070001_messaging_v1_foundation.sql');
  const service = read('backend/src/services/messaging.service.js');
  const context = read('front/mi-front-limpio/context/MessagingContext.tsx');
  const inbox = read('front/mi-front-limpio/screens/messages/MessagesInboxScreen.tsx');
  const conversation = read('front/mi-front-limpio/screens/messages/MessagesConversationScreen.tsx');
  const tabs = read('front/mi-front-limpio/navigation/HomeTabNavigator.tsx');

  expect(migration.includes('messaging_one_active_household_conversation'), 'Missing household-thread uniqueness constraint');
  expect(migration.includes('messaging_one_direct_per_membership_pair'), 'Missing canonical direct-thread uniqueness constraint');
  expect(migration.includes('unique (conversation_id, sender_membership_id, client_message_id)'), 'Missing optimistic retry dedupe constraint');
  expect(migration.includes('messaging_conversations_select_authorized'), 'Missing conversation RLS policy');
  expect(migration.includes('messaging_messages_select_authorized'), 'Missing message RLS policy');
  expect(migration.includes("alter publication supabase_realtime add table public.messaging_messages"), 'Messages are not in Realtime publication');
  expect(service.includes('p_client_message_id: payload.client_message_id'), 'Backend no longer forwards only the client mutation id');
  expect(!service.includes('p_sender_membership_id'), 'Backend must never accept a caller supplied sender membership');
  expect(context.includes('supabase.realtime.setAuth(accessToken)'), 'Realtime JWT is not synchronized before subscriptions');
  expect(context.includes('isSameMessage') && context.includes('client_message_id'), 'Optimistic/HTTP/Realtime dedupe is missing');
  expect(context.includes('a.sequence - b.sequence || a.id.localeCompare(b.id)'), 'Message ordering must use server sequence then id');
  expect(context.includes('[Messaging] send.optimistic') && context.includes('[Messaging] realtime.received'), 'Development messaging instrumentation is missing');
  expect(inbox.includes('navigation.goBack()'), 'Inbox back navigation must preserve the origin');
  expect(conversation.includes('sendTaskMessage(conversationId, task.id)') && conversation.includes("disabled={label !== 'Tarea'}"), 'Task must be the only enabled contextual action');
  expect(tabs.includes("icon=\"chatbubbles-outline\"") && !tabs.includes('accessibilityLabel="Buscar en HomePlus"'), 'Standard global header must prioritize Messages over search');

  console.log('MESSAGING_FOUNDATION_CONTRACTS=PASS');
} catch (error) {
  console.error(`MESSAGING_FOUNDATION_CONTRACTS=FAIL: ${error.message}`);
  process.exitCode = 1;
}
