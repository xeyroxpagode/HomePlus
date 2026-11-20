export type HomiMessageRole = 'user' | 'assistant' | 'system';
export type HomiMessageStatus = 'pending' | 'sent' | 'failed' | 'cancelled';
export type HomiMessageKind = 'text' | 'attachment' | 'see_result' | 'tool_result';

/**
 * Stable Planner task projection of the Homi READ tool layer.
 *
 * Only the fields the TaskCard renders are declared as required; the tool
 * result carries the canonical task DTO, which keeps additional fields.
 */
export type HomiTaskDto = {
  id: string;
  title: string;
  status: string;
  description?: string | null;
  priority?: string | null;
  due_date?: string | null;
  due_time?: string | null;
  assigned_to_member_id?: string | null;
  created_by_member_id?: string | null;
  requires_verification?: boolean;
};

export type HomiToolResult = {
  tool_id: string;
  /** The canonical tool invocation result (e.g. `{ tasks: [...] }`). */
  result: Record<string, unknown>;
};

export type HomiAttachment = {
  attachment_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes?: number;
  status?: string;
};

export type SeeResult = {
  attachment_id: string;
  task: string;
  status: 'success' | 'error';
  artifact_type?: string;
  text?: string;
  fields?: Record<string, unknown>;
  warnings?: string[];
  engine?: string;
  provider_id?: string;
  error?: string;
  message?: string;
  retryable?: boolean;
  _continuity?: boolean;
};

export type HomiMessage = {
  id: string;
  role: HomiMessageRole;
  text: string;
  status: HomiMessageStatus;
  kind?: HomiMessageKind;
  attachment?: HomiAttachment;
  see_result?: SeeResult;
  tool_result?: HomiToolResult;
  /** Voice provenance: the turn arrived as audio. */
  via_voice?: boolean;
  /** ISO timestamp of the turn, used for the message meta row. */
  created_at?: string;
  turn_id?: string;
};

let messageCounter = 0;

export const createHomiMessageId = (): string => {
  messageCounter += 1;
  return `homi_msg_${Date.now()}_${messageCounter}`;
};

export const createHomiMessage = (input: {
  role: HomiMessageRole;
  text: string;
  status?: HomiMessageStatus;
  kind?: HomiMessageKind;
  attachment?: HomiAttachment;
  see_result?: SeeResult;
  tool_result?: HomiToolResult;
  via_voice?: boolean;
  created_at?: string;
  turn_id?: string;
}): HomiMessage => ({
  id: createHomiMessageId(),
  role: input.role,
  text: input.text,
  status: input.status ?? 'pending',
  kind: input.kind ?? 'text',
  attachment: input.attachment,
  see_result: input.see_result,
  tool_result: input.tool_result,
  via_voice: input.via_voice,
  created_at: input.created_at,
  turn_id: input.turn_id,
});
