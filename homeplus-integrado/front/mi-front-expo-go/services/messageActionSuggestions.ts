/**
 * Future Homi extension point. Suggestions are deliberately ephemeral: M2
 * neither derives AI intent nor persists confidence, so no suggestion can
 * create an action without an explicit member confirmation.
 */
import type { Message } from './messages';

export type MessageActionSuggestion = {
  message_id: string;
  suggested_action_type: 'task' | 'shopping' | 'plan' | 'place' | 'file';
  source: 'homi';
  confidence?: number;
};

export type MessageActionSuggester = (message: Message) => readonly MessageActionSuggestion[];

export const noMessageActionSuggestions: MessageActionSuggester = () => [];
