export const HOMI_CONTRACT_VERSION = '1.0.0';

export type HomiProposalAction = 'confirm' | 'cancel';

export const isHomiProposalAction = (
  value: unknown,
): value is HomiProposalAction =>
  value === 'confirm' || value === 'cancel';

export type HomiDecisionKind =
  | 'direct_response'
  | 'clarify'
  | 'tool_request'
  | 'action_proposal'
  | 'action_executed'
  | 'blocked';

export type HomiDirectResponseResult = {
  answer: string;
  decision_kind: 'direct_response';
};

export type HomiClarifyResult = {
  answer: string;
  decision_kind: 'clarify';
};

export type HomiToolRequestResult = {
  answer: string;
  decision_kind: 'tool_request';
  source_tool_id: string;
  tool_call_id: string;
  grounded: boolean;
  truncated: boolean;
};

export type HomiActionProposalResult = {
  answer: string;
  decision_kind: 'action_proposal';
  proposal?: unknown;
  status?: string;
};

export type HomiActionExecutedResult = {
  answer: string;
  decision_kind: 'action_executed';
  proposal?: unknown;
  result?: unknown;
  status?: string;
  error?: unknown;
};

export type HomiBlockedResult = {
  answer: string;
  decision_kind: 'blocked';
  error?: unknown;
  status?: string;
};

export type HomiResult =
  | HomiDirectResponseResult
  | HomiClarifyResult
  | HomiToolRequestResult
  | HomiActionProposalResult
  | HomiActionExecutedResult
  | HomiBlockedResult;

export type HomiRequestContext = {
  conversation_id: string;
  actor_id: string;
  household_id: string;
  request_id?: string;
  trace_id?: string;
  turn_id?: string;
  timestamp?: string;
};

export type HomiRequestEnvelope = {
  contract_version?: string;
  context: HomiRequestContext;
  capability: 'think';
  operation: 'infer_with_tools';
  payload: {
    text: string;
    proposal_action?: HomiProposalAction;
  };
};

export type HomiSuccessEnvelope = {
  status: 'SUCCESS';
  result: HomiResult;
};

export type HomiErrorShape = {
  code: string;
  message: string;
  retryable: boolean;
  node_id?: string;
  provider_id?: string;
  details?: unknown;
};

export type HomiErrorEnvelope = {
  status: 'ERROR';
  error: HomiErrorShape;
};

export type HomiResponseEnvelope = HomiSuccessEnvelope | HomiErrorEnvelope;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const isHomiDirectResponseResult = (value: unknown): value is HomiDirectResponseResult =>
  isRecord(value) &&
  typeof value.answer === 'string' &&
  value.decision_kind === 'direct_response';

export const isHomiClarifyResult = (value: unknown): value is HomiClarifyResult =>
  isRecord(value) &&
  typeof value.answer === 'string' &&
  value.decision_kind === 'clarify';

export const isHomiToolRequestResult = (value: unknown): value is HomiToolRequestResult =>
  isRecord(value) &&
  typeof value.answer === 'string' &&
  value.decision_kind === 'tool_request' &&
  typeof value.source_tool_id === 'string' &&
  typeof value.tool_call_id === 'string' &&
  typeof value.grounded === 'boolean' &&
  typeof value.truncated === 'boolean';

export const isHomiActionProposalResult = (value: unknown): value is HomiActionProposalResult =>
  isRecord(value) &&
  typeof value.answer === 'string' &&
  value.decision_kind === 'action_proposal';

export const isHomiActionExecutedResult = (value: unknown): value is HomiActionExecutedResult =>
  isRecord(value) &&
  typeof value.answer === 'string' &&
  value.decision_kind === 'action_executed';

export const isHomiBlockedResult = (value: unknown): value is HomiBlockedResult =>
  isRecord(value) &&
  typeof value.answer === 'string' &&
  value.decision_kind === 'blocked';

export const isHomiResult = (value: unknown): value is HomiResult =>
  isHomiDirectResponseResult(value) ||
  isHomiClarifyResult(value) ||
  isHomiToolRequestResult(value) ||
  isHomiActionProposalResult(value) ||
  isHomiActionExecutedResult(value) ||
  isHomiBlockedResult(value);

export const isHomiSuccessEnvelope = (value: unknown): value is HomiSuccessEnvelope =>
  isRecord(value) &&
  value.status === 'SUCCESS' &&
  isHomiResult(value.result);

export const isHomiErrorEnvelope = (value: unknown): value is HomiErrorEnvelope =>
  isRecord(value) &&
  value.status === 'ERROR' &&
  isRecord(value.error) &&
  typeof (value.error as Record<string, unknown>).code === 'string' &&
  typeof (value.error as Record<string, unknown>).message === 'string' &&
  typeof (value.error as Record<string, unknown>).retryable === 'boolean';

export const isHomiResponseEnvelope = (value: unknown): value is HomiResponseEnvelope =>
  isHomiSuccessEnvelope(value) || isHomiErrorEnvelope(value);

export const isHomiSuccessResponse = isHomiSuccessEnvelope;
export const isHomiErrorResponse = isHomiErrorEnvelope;
export const isHomiEnvelope = isHomiResponseEnvelope;

// T23 — Attachment and SEE result types

export type AttachmentUploadResult = {
  attachment_id: string;
  status: string;
  mime_type: string;
  size_bytes: number;
  original_filename: string;
  created_at: string;
  expires_at: string;
};

export type AttachmentReference = {
  attachment_id: string;
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

// Extended payload for /invoke with attachments and SEE results
export type HomiInvokePayload = {
  text: string;
  attachments?: AttachmentReference[];
  proposal_action?: HomiProposalAction;
  _see_results?: SeeResult[];
};

// Extended request envelope that supports attachments
export type HomiRequestEnvelopeWithAttachments = {
  contract_version?: string;
  context: HomiRequestContext;
  capability: 'think';
  operation: 'infer_with_tools';
  payload: HomiInvokePayload;
};

// Extended result types that include SEE results
export type HomiDirectResponseResultWithSee = HomiDirectResponseResult & {
  see_results?: SeeResult[];
};

export type HomiClarifyResultWithSee = HomiClarifyResult & {
  see_results?: SeeResult[];
};

export type HomiToolRequestResultWithSee = HomiToolRequestResult & {
  see_results?: SeeResult[];
};

export type HomiResultWithSee =
  | HomiDirectResponseResultWithSee
  | HomiClarifyResultWithSee
  | HomiToolRequestResultWithSee;

export type HomiSuccessEnvelopeWithSee = {
  status: 'SUCCESS';
  result: HomiResultWithSee;
  correlation?: {
    conversation_id: string;
    turn_id: string;
  };
};

export type HomiResponseEnvelopeWithSee = HomiSuccessEnvelopeWithSee | HomiErrorEnvelope;

// Type guards for SEE results
export const isSeeResult = (value: unknown): value is SeeResult => {
  if (!isRecord(value)) return false;
  if (typeof value.attachment_id !== 'string') return false;
  if (typeof value.task !== 'string') return false;
  if (typeof value.status !== 'string') return false;
  return true;
};

export const isHomiResultWithSee = (value: unknown): value is HomiResultWithSee => {
  if (!isHomiResult(value)) return false;
  const result = value as HomiResultWithSee;
  if (result.see_results !== undefined) {
    if (!Array.isArray(result.see_results)) return false;
    return result.see_results.every(isSeeResult);
  }
  return true;
};

export const isHomiSuccessEnvelopeWithSee = (value: unknown): value is HomiSuccessEnvelopeWithSee => {
  if (!isHomiSuccessEnvelope(value)) return false;
  const envelope = value as HomiSuccessEnvelopeWithSee;
  return isHomiResultWithSee(envelope.result);
};

export const isHomiResponseEnvelopeWithSee = (value: unknown): value is HomiResponseEnvelopeWithSee => {
  return isHomiSuccessEnvelopeWithSee(value) || isHomiErrorEnvelope(value);
};

// Re-export original guard with alias for clarity
export const isHomiRequestEnvelopeBase = (value: unknown): value is HomiRequestEnvelope => {
  if (!isRecord(value)) return false;
  if (value.capability !== 'think') return false;
  if (value.operation !== 'infer_with_tools') return false;
  if (!isRecord(value.context)) return false;
  const ctx = value.context as Record<string, unknown>;
  if (typeof ctx.conversation_id !== 'string') return false;
  if (typeof ctx.actor_id !== 'string') return false;
  if (typeof ctx.household_id !== 'string') return false;
  if (!isRecord(value.payload)) return false;
  const payload = value.payload as Record<string, unknown>;
  if (typeof payload.text !== 'string') return false;
  // Attachments and _see_results are optional
  if (payload.attachments !== undefined) {
    if (!Array.isArray(payload.attachments)) return false;
    for (const att of payload.attachments) {
      if (!isRecord(att) || typeof att.attachment_id !== 'string') return false;
    }
  }
  return true;
};
