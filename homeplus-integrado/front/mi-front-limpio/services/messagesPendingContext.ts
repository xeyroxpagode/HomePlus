import type { Message } from './messages';

// A pending conversation item is a reference, never a copied domain object.
// New context types extend this union without making parallel task/shopping
// stores inside Messaging.
export type PendingConversationContext = {
  conversationId: string;
  type: 'task';
  entityId: string;
  messageId: string;
  state: 'active';
};

export const derivePendingConversationContexts = (messages: readonly Message[]): PendingConversationContext[] =>
  messages
    .filter((message): message is Message & { type: 'task'; context_entity_id: string } =>
      message.type === 'task' && Boolean(message.context_entity_id) && !message.deleted_at,
    )
    .map((message) => ({
      conversationId: message.conversation_id,
      type: 'task' as const,
      entityId: message.context_entity_id,
      messageId: message.id,
      state: 'active' as const,
    }));
