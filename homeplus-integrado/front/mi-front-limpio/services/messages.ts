import { OPERATION_KINDS, requestJson } from './api';

export type MessageMember = {
  membership_id: string;
  person_id: string;
  display_name: string;
  avatar_url: string | null;
  role: string | null;
};

export type MessageReadState = {
  last_read_sequence: number;
  last_read_at: string | null;
  unread_count: number;
};

export type Conversation = {
  id: string;
  household_id: string;
  type: 'household' | 'direct';
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  last_message: { preview: string; sender_membership_id: string; created_at: string } | null;
  direct_partner: MessageMember | null;
  read_state: MessageReadState;
};

export type Message = {
  id: string;
  conversation_id: string;
  sender_membership_id: string;
  sender: MessageMember | null;
  type: 'text' | 'task' | 'image' | 'audio' | 'file';
  body: string;
  context_entity_id: string | null;
  client_message_id: string;
  sequence: number;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  reactions?: { reaction_type: 'like' | 'thanks' | 'acknowledge'; count: number; mine: boolean }[];
  attachments?: MessagingAttachment[];
  delivery?: 'sending' | 'sent' | 'failed';
};
export type MessagingAttachment = {
  id: string; message_id: string | null; household_id: string; conversation_id: string;
  kind: 'image' | 'audio' | 'file'; mime_type: string; original_name: string; size_bytes: number;
  width: number | null; height: number | null; duration_ms: number | null;
  lifecycle: 'uploading' | 'uploaded' | 'committed' | 'failed'; created_at: string;
  local_uri?: string; upload_progress?: number;
};

export type ConversationsResponse = { conversations: Conversation[]; unread_count: number };
export type MessagesResponse = { messages: Message[]; page: { has_more: boolean; next_before_sequence: number | null } };

export const listConversations = (accessToken: string) =>
  requestJson<ConversationsResponse>('/api/messages/conversations', { accessToken });

export const getConversation = (accessToken: string, conversationId: string) =>
  requestJson<{ conversation: Conversation }>(`/api/messages/conversations/${conversationId}`, { accessToken });

export const ensureDirectConversation = (accessToken: string, otherMembershipId: string) =>
  requestJson<{ conversation: Conversation }>('/api/messages/directs/ensure', {
    method: 'POST',
    accessToken,
    operationKind: OPERATION_KINDS.CREATE_IDEMPOTENT,
    body: { other_membership_id: otherMembershipId },
  });

export const listMessages = (accessToken: string, conversationId: string, beforeSequence?: number) => {
  const query = beforeSequence ? `?before_sequence=${beforeSequence}` : '';
  return requestJson<MessagesResponse>(`/api/messages/conversations/${conversationId}/messages${query}`, { accessToken });
};

export const sendMessage = (accessToken: string, conversationId: string, body: string, clientMessageId: string) =>
  requestJson<{ message: Message }>(`/api/messages/conversations/${conversationId}/messages`, {
    method: 'POST',
    accessToken,
    operationKind: OPERATION_KINDS.CREATE_IDEMPOTENT,
    idempotencyKey: clientMessageId,
    body: { type: 'text', body, client_message_id: clientMessageId },
  });

export const sendTaskMessage = (accessToken: string, conversationId: string, taskId: string, clientMessageId: string) =>
  requestJson<{ message: Message }>(`/api/messages/conversations/${conversationId}/messages`, {
    method: 'POST', accessToken, operationKind: OPERATION_KINDS.CREATE_IDEMPOTENT, idempotencyKey: clientMessageId,
    body: { type: 'task', context_entity_id: taskId, client_message_id: clientMessageId },
  });

export const sendAttachmentMessage = (accessToken: string, conversationId: string, type: 'image' | 'audio' | 'file', attachmentId: string, clientMessageId: string) =>
  requestJson<{ message: Message }>(`/api/messages/conversations/${conversationId}/messages`, {
    method: 'POST', accessToken, operationKind: OPERATION_KINDS.CREATE_IDEMPOTENT, idempotencyKey: clientMessageId,
    body: { type, attachment_id: attachmentId, client_message_id: clientMessageId },
  });

export const registerMessageAttachment = (accessToken: string, conversationId: string, body: {
  kind: 'image' | 'audio' | 'file'; mime_type: string; original_name: string; size_bytes: number;
  client_attachment_id: string; width?: number | null; height?: number | null; duration_ms?: number | null;
}) => requestJson<{ attachment: MessagingAttachment }>(`/api/messages/conversations/${conversationId}/attachments`, {
  method: 'POST', accessToken, operationKind: OPERATION_KINDS.CREATE_IDEMPOTENT, idempotencyKey: body.client_attachment_id, body,
});

export const authorizeMessageAttachmentUpload = (accessToken: string, attachmentId: string) => requestJson<{ attachment: MessagingAttachment; signed_upload_url: string }>(`/api/messages/attachments/${attachmentId}/upload`, { method: 'POST', accessToken });
export const verifyMessageAttachmentUpload = (accessToken: string, attachmentId: string) => requestJson<{ attachment: MessagingAttachment; verified: boolean }>(`/api/messages/attachments/${attachmentId}/verify`, { method: 'POST', accessToken });
export const cancelMessageAttachmentUpload = (accessToken: string, attachmentId: string) => requestJson<{ cancelled: boolean; committed: boolean }>(`/api/messages/attachments/${attachmentId}/cancel`, { method: 'POST', accessToken });
export const getMessageAttachmentDownload = (accessToken: string, attachmentId: string) => requestJson<{ attachment: MessagingAttachment; signed_url: string }>(`/api/messages/attachments/${attachmentId}/download`, { accessToken });
export const linkMessageToTask = (accessToken: string, messageId: string, taskId: string) => requestJson<{ action: { id: string; entity_id: string } }>(`/api/messages/messages/${messageId}/actions/task`, { method: 'POST', accessToken, body: { task_id: taskId } });

export const markConversationRead = (accessToken: string, conversationId: string, throughSequence: number) =>
  requestJson<{ read_state: Pick<MessageReadState, 'last_read_sequence' | 'last_read_at'> }>(
    `/api/messages/conversations/${conversationId}/read`,
    { method: 'POST', accessToken, body: { through_sequence: throughSequence } },
  );

export const toggleMessageReaction = (accessToken: string, messageId: string, reactionType: 'like' | 'thanks' | 'acknowledge') =>
  requestJson<{ state: 'set' | 'removed' }>(`/api/messages/messages/${messageId}/reaction`, {
    method: 'POST', accessToken, body: { reaction_type: reactionType },
  });

/** UUID v4 without a platform-specific dependency; it is only an idempotency key. */
export const createClientMessageId = () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
  const value = Math.floor(Math.random() * 16);
  const nibble = character === 'x' ? value : (value & 0x3) | 0x8;
  return nibble.toString(16);
});
