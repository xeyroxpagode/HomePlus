import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { useAuth } from './AuthContext';
import { useHousehold } from './HouseholdContext';
import { supabase } from '../supabase';
import {
  createClientMessageId,
  ensureDirectConversation as ensureDirectRequest,
  listConversations,
  listMessages,
  markConversationRead as markReadRequest,
  toggleMessageReaction as toggleReactionRequest,
  sendMessage as sendMessageRequest,
  sendTaskMessage as sendTaskMessageRequest,
  type MessagingAttachment,
  type Conversation,
  type Message,
} from '../services/messages';
import { uploadAndSendMessageMedia, type LocalMessageMedia } from '../services/richMessagingMedia';

type ConversationMessageMap = Record<string, Message[]>;
type MessagingContextValue = {
  conversationsById: Record<string, Conversation>;
  messagesByConversationId: ConversationMessageMap;
  orderedConversations: Conversation[];
  unreadCount: number;
  loadingInbox: boolean;
  inboxError: string | null;
  refreshInbox: () => Promise<void>;
  loadMessages: (conversationId: string, beforeSequence?: number) => Promise<void>;
  sendTextMessage: (conversationId: string, body: string, retryClientMessageId?: string) => Promise<void>;
  sendTaskMessage: (conversationId: string, taskId: string, retryClientMessageId?: string) => Promise<void>;
  sendMediaMessage: (conversationId: string, media: LocalMessageMedia, retryClientMessageId?: string, retryAttachmentId?: string) => Promise<void>;
  markRead: (conversationId: string, throughSequence: number) => Promise<void>;
  toggleReaction: (conversationId: string, messageId: string, reactionType: 'like' | 'thanks' | 'acknowledge') => Promise<void>;
  ensureDirect: (otherMembershipId: string) => Promise<Conversation>;
  subscribeConversation: (conversationId: string) => () => void;
};

const MessagingContext = createContext<MessagingContextValue | null>(null);

const isSameMessage = (left: Message, right: Message) => left.id === right.id
  || (left.client_message_id === right.client_message_id && left.sender_membership_id === right.sender_membership_id);

const sortMessages = (messages: Message[]) => [...messages].sort((a, b) => (
  a.sequence - b.sequence || a.id.localeCompare(b.id)
));

const messageFromRealtime = (row: Record<string, unknown>): Message | null => {
  if (typeof row.id !== 'string' || typeof row.conversation_id !== 'string' || typeof row.sender_membership_id !== 'string'
    || typeof row.body !== 'string' || typeof row.client_message_id !== 'string' || typeof row.sequence !== 'number') return null;
  return {
    id: row.id,
    conversation_id: row.conversation_id,
    sender_membership_id: row.sender_membership_id,
    sender: null,
    type: ['task', 'image', 'audio', 'file'].includes(String(row.message_type)) ? row.message_type as Message['type'] : 'text',
    body: row.body,
    context_entity_id: typeof row.context_entity_id === 'string' ? row.context_entity_id : null,
    client_message_id: row.client_message_id,
    sequence: row.sequence,
    created_at: typeof row.created_at === 'string' ? row.created_at : new Date().toISOString(),
    edited_at: typeof row.edited_at === 'string' ? row.edited_at : null,
    deleted_at: typeof row.deleted_at === 'string' ? row.deleted_at : null,
    reactions: [], attachments: [],
    delivery: 'sent',
  };
};

export function MessagingProvider({ children }: { children: React.ReactNode }) {
  const { session, authMe } = useAuth();
  const { currentHousehold } = useHousehold();
  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? authMe?.active_household?.id ?? null;
  const membershipId = useMemo(() => authMe?.memberships.find((member) => member.household_id === householdId && member.status === 'active')?.id ?? null, [authMe?.memberships, householdId]);
  const scopeKey = accessToken && householdId && membershipId ? `${householdId}:${membershipId}` : null;
  const scopeRef = useRef(scopeKey);
  const [conversationsById, setConversationsById] = useState<Record<string, Conversation>>({});
  const [messagesByConversationId, setMessagesByConversationId] = useState<ConversationMessageMap>({});
  const [loadingInbox, setLoadingInbox] = useState(false);
  const [inboxError, setInboxError] = useState<string | null>(null);
  const [realtimeAccessToken, setRealtimeAccessToken] = useState<string | null>(null);

  // Realtime does not inherit an HTTP Authorization header.  Set the current
  // authenticated JWT before joining Postgres Changes so its RLS evaluation is
  // performed as the signed-in household member rather than as `anon`.
  useEffect(() => {
    let active = true;
    if (!accessToken) {
      setRealtimeAccessToken(null);
      return () => { active = false; };
    }

    setRealtimeAccessToken(null);
    void supabase.realtime.setAuth(accessToken)
      .then(() => {
        if (active) setRealtimeAccessToken(accessToken);
      })
      .catch(() => {
        if (active) setRealtimeAccessToken(null);
      });

    return () => { active = false; };
  }, [accessToken]);

  const refreshInbox = useCallback(async () => {
    if (!accessToken || !scopeKey) return;
    setLoadingInbox(true);
    try {
      const response = await listConversations(accessToken);
      if (scopeRef.current !== scopeKey) return;
      setConversationsById(Object.fromEntries(response.conversations.map((conversation) => [conversation.id, conversation])));
      setInboxError(null);
    } catch (error) {
      if (scopeRef.current === scopeKey) setInboxError(error instanceof Error ? error.message : 'No pudimos cargar los mensajes.');
    } finally {
      if (scopeRef.current === scopeKey) setLoadingInbox(false);
    }
  }, [accessToken, scopeKey]);

  useEffect(() => {
    scopeRef.current = scopeKey;
    setConversationsById({});
    setMessagesByConversationId({});
    setInboxError(null);
    if (scopeKey) void refreshInbox();
  }, [refreshInbox, scopeKey]);

  // Inbox is refreshed after a database event, not by polling. The database
  // policy, rather than this household filter, is the authorization boundary.
  useEffect(() => {
    if (!householdId || !scopeKey || realtimeAccessToken !== accessToken) return undefined;
    const channel = supabase
      .channel(`messaging-inbox:${householdId}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'messaging_conversations', filter: `household_id=eq.${householdId}` }, () => {
        void refreshInbox();
      })
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, [accessToken, householdId, realtimeAccessToken, refreshInbox, scopeKey]);

  const loadMessages = useCallback(async (conversationId: string, beforeSequence?: number) => {
    if (!accessToken) return;
    const response = await listMessages(accessToken, conversationId, beforeSequence);
    setMessagesByConversationId((previous) => {
      const current = previous[conversationId] ?? [];
      const merged = [...current];
      response.messages.forEach((incoming) => {
        const index = merged.findIndex((item) => isSameMessage(item, incoming));
        if (index >= 0) merged[index] = { ...merged[index], ...incoming, delivery: 'sent' };
        else merged.push({ ...incoming, delivery: 'sent' });
      });
      return { ...previous, [conversationId]: sortMessages(merged) };
    });
  }, [accessToken]);

  const receiveMessage = useCallback((incoming: Message, source: 'http' | 'realtime' = 'realtime') => {
    setMessagesByConversationId((previous) => {
      const current = previous[incoming.conversation_id];
      if (!current) return previous;
      const index = current.findIndex((item) => isSameMessage(item, incoming));
      if (__DEV__) console.log('[Messaging] message.merged', {
        conversationId: incoming.conversation_id,
        messageId: incoming.id,
        source,
        reconciled: index >= 0,
      });
      const merged: Message[] = index >= 0
        ? current.map((item, itemIndex): Message => itemIndex === index ? { ...item, ...incoming, delivery: 'sent' } : item)
        : [...current, incoming];
      return { ...previous, [incoming.conversation_id]: sortMessages(merged) };
    });
  }, []);

  const subscribeConversation = useCallback((conversationId: string) => {
    if (!accessToken || realtimeAccessToken !== accessToken) return () => undefined;
    const channel = supabase
      .channel(`messaging-conversation:${conversationId}`)
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'messaging_messages', filter: `conversation_id=eq.${conversationId}` }, (payload) => {
        const incoming = messageFromRealtime(payload.new as Record<string, unknown>);
        if (incoming) {
          if (__DEV__) console.log('[Messaging] realtime.received', { conversationId: incoming.conversation_id, messageId: incoming.id });
          receiveMessage(incoming, 'realtime');
          if (incoming.type !== 'text') void loadMessages(conversationId);
        }
      })
      .on('postgres_changes', { event: '*', schema: 'public', table: 'messaging_message_reactions' }, () => {
        // Reactions are authorized by the same conversation RLS gate. Re-read
        // the bounded message page to obtain canonical aggregate state.
        void loadMessages(conversationId);
      })
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, [accessToken, loadMessages, realtimeAccessToken, receiveMessage]);

  const sendTextMessage = useCallback(async (conversationId: string, rawBody: string, retryClientMessageId?: string) => {
    if (!accessToken || !membershipId) return;
    const body = rawBody.trim();
    if (!body) return;
    const clientMessageId = retryClientMessageId ?? createClientMessageId();
    const optimistic: Message = {
      id: `pending:${clientMessageId}`,
      conversation_id: conversationId,
      sender_membership_id: membershipId,
      sender: null,
      type: 'text', body, context_entity_id: null, client_message_id: clientMessageId, sequence: Number.MAX_SAFE_INTEGER,
      created_at: new Date().toISOString(), edited_at: null, deleted_at: null, delivery: 'sending',
    };
    setMessagesByConversationId((previous) => {
      const current = previous[conversationId] ?? [];
      const exists = current.some((item) => item.client_message_id === clientMessageId && item.sender_membership_id === membershipId);
      return exists ? previous : { ...previous, [conversationId]: sortMessages([...current, optimistic]) };
    });
    if (__DEV__) console.log('[Messaging] send.optimistic', { conversationId, clientMessageId });
    try {
      const response = await sendMessageRequest(accessToken, conversationId, body, clientMessageId);
      if (__DEV__) console.log('[Messaging] send.confirmed', { conversationId, messageId: response.message.id, clientMessageId });
      receiveMessage({ ...response.message, delivery: 'sent' }, 'http');
      void refreshInbox();
    } catch {
      setMessagesByConversationId((previous) => ({
        ...previous,
        [conversationId]: (previous[conversationId] ?? []).map((message) => (
          message.client_message_id === clientMessageId && message.sender_membership_id === membershipId
            ? { ...message, delivery: 'failed' }
            : message
        )),
      }));
    }
  }, [accessToken, membershipId, receiveMessage, refreshInbox]);

  const sendTaskMessage = useCallback(async (conversationId: string, taskId: string, retryClientMessageId?: string) => {
    if (!accessToken || !membershipId) return;
    const clientMessageId = retryClientMessageId ?? createClientMessageId();
    const optimistic: Message = { id: `pending:${clientMessageId}`, conversation_id: conversationId, sender_membership_id: membershipId, sender: null, type: 'task', body: '', context_entity_id: taskId, client_message_id: clientMessageId, sequence: Number.MAX_SAFE_INTEGER, created_at: new Date().toISOString(), edited_at: null, deleted_at: null, delivery: 'sending' };
    setMessagesByConversationId((previous) => {
      const current = previous[conversationId] ?? [];
      const exists = current.some((item) => item.client_message_id === clientMessageId && item.sender_membership_id === membershipId);
      return exists ? previous : { ...previous, [conversationId]: sortMessages([...current, optimistic]) };
    });
    if (__DEV__) console.log('[Messaging] send.optimistic', { conversationId, clientMessageId, type: 'task' });
    try {
      const response = await sendTaskMessageRequest(accessToken, conversationId, taskId, clientMessageId);
      if (__DEV__) console.log('[Messaging] send.confirmed', { conversationId, messageId: response.message.id, clientMessageId, type: 'task' });
      receiveMessage({ ...response.message, delivery: 'sent' }, 'http');
      void refreshInbox();
    } catch {
      setMessagesByConversationId((previous) => ({ ...previous, [conversationId]: (previous[conversationId] ?? []).map((message) => message.client_message_id === clientMessageId ? { ...message, delivery: 'failed' } : message) }));
    }
  }, [accessToken, membershipId, receiveMessage, refreshInbox]);

  const sendMediaMessage = useCallback(async (conversationId: string, media: LocalMessageMedia, retryClientMessageId?: string, retryAttachmentId?: string) => {
    if (!accessToken || !membershipId) return;
    const clientMessageId = retryClientMessageId ?? createClientMessageId();
    const clientAttachmentId = retryAttachmentId ?? createClientMessageId();
    const attachment: MessagingAttachment = {
      id: `pending:${clientAttachmentId}`, message_id: null, household_id: householdId ?? '', conversation_id: conversationId,
      kind: media.kind, mime_type: media.mimeType, original_name: media.originalName, size_bytes: media.sizeBytes,
      width: media.width ?? null, height: media.height ?? null, duration_ms: media.durationMs ?? null,
      lifecycle: 'uploading', created_at: new Date().toISOString(), local_uri: media.uri, upload_progress: 0,
    };
    const optimistic: Message = { id: `pending:${clientMessageId}`, conversation_id: conversationId, sender_membership_id: membershipId, sender: null, type: media.kind, body: '', context_entity_id: null, client_message_id: clientMessageId, sequence: Number.MAX_SAFE_INTEGER, created_at: new Date().toISOString(), edited_at: null, deleted_at: null, reactions: [], attachments: [attachment], delivery: 'sending' };
    setMessagesByConversationId((previous) => {
      const current = previous[conversationId] ?? [];
      return current.some((item) => item.client_message_id === clientMessageId && item.sender_membership_id === membershipId) ? previous : { ...previous, [conversationId]: sortMessages([...current, optimistic]) };
    });
    try {
      const message = await uploadAndSendMessageMedia({ accessToken, conversationId, media, clientMessageId, clientAttachmentId, onProgress: (uploadProgress) => {
        setMessagesByConversationId((previous) => ({ ...previous, [conversationId]: (previous[conversationId] ?? []).map((item) => item.client_message_id === clientMessageId ? { ...item, attachments: item.attachments?.map((value) => ({ ...value, upload_progress: uploadProgress })) } : item) }));
      } });
      receiveMessage({ ...message, delivery: 'sent' }, 'http');
      void refreshInbox();
    } catch {
      setMessagesByConversationId((previous) => ({ ...previous, [conversationId]: (previous[conversationId] ?? []).map((item) => item.client_message_id === clientMessageId ? { ...item, delivery: 'failed', attachments: item.attachments?.map((value) => ({ ...value, lifecycle: 'failed' })) } : item) }));
    }
  }, [accessToken, householdId, membershipId, receiveMessage, refreshInbox]);

  const markRead = useCallback(async (conversationId: string, throughSequence: number) => {
    if (!accessToken || throughSequence < 0) return;
    const response = await markReadRequest(accessToken, conversationId, throughSequence);
    setConversationsById((previous) => {
      const conversation = previous[conversationId];
      if (!conversation) return previous;
      // Do not blindly zero unread: an incoming remote message can arrive
      // while the read cursor mutation is in flight.  Count only messages
      // after the canonical cursor and never count the member's own sends.
      const unreadAfterCursor = (messagesByConversationId[conversationId] ?? []).filter((message) => (
        message.sequence > response.read_state.last_read_sequence
        && message.sender_membership_id !== membershipId
        && message.delivery !== 'sending'
      )).length;
      return { ...previous, [conversationId]: {
        ...conversation,
        read_state: { ...conversation.read_state, ...response.read_state, unread_count: unreadAfterCursor },
      } };
    });
  }, [accessToken, membershipId, messagesByConversationId]);

  const toggleReaction = useCallback(async (conversationId: string, messageId: string, reactionType: 'like' | 'thanks' | 'acknowledge') => {
    if (!accessToken || !membershipId) return;
    // The server toggle is canonical. A bounded reload reconciles a fast
    // double-tap or concurrent member action without client-side counters.
    await toggleReactionRequest(accessToken, messageId, reactionType);
    await loadMessages(conversationId);
  }, [accessToken, loadMessages, membershipId]);

  const ensureDirect = useCallback(async (otherMembershipId: string) => {
    if (!accessToken) throw new Error('Tu sesión ya no está activa.');
    const response = await ensureDirectRequest(accessToken, otherMembershipId);
    setConversationsById((previous) => ({ ...previous, [response.conversation.id]: response.conversation }));
    return response.conversation;
  }, [accessToken]);

  const orderedConversations = useMemo(() => Object.values(conversationsById).sort((a, b) => (
    new Date(b.last_activity_at).getTime() - new Date(a.last_activity_at).getTime() || b.id.localeCompare(a.id)
  )), [conversationsById]);
  const unreadCount = useMemo(() => orderedConversations.reduce((total, conversation) => total + conversation.read_state.unread_count, 0), [orderedConversations]);
  const value = useMemo<MessagingContextValue>(() => ({
    conversationsById, messagesByConversationId, orderedConversations, unreadCount, loadingInbox, inboxError,
    refreshInbox, loadMessages, sendTextMessage, sendTaskMessage, sendMediaMessage, markRead, toggleReaction, ensureDirect, subscribeConversation,
  }), [conversationsById, ensureDirect, inboxError, loadMessages, loadingInbox, markRead, messagesByConversationId, orderedConversations, refreshInbox, sendTextMessage, sendTaskMessage, sendMediaMessage, subscribeConversation, toggleReaction, unreadCount]);

  return <MessagingContext.Provider value={value}>{children}</MessagingContext.Provider>;
}

export const useMessaging = () => {
  const value = useContext(MessagingContext);
  if (!value) throw new Error('useMessaging must be used inside MessagingProvider');
  return value;
};
