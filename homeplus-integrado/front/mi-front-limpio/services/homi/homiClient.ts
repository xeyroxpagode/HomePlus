import { requestJson, OPERATION_KINDS, ApiError } from '../api';
import {
  HOMI_CONTRACT_VERSION,
  isHomiResponseEnvelopeWithSee,
  isHomiSuccessEnvelopeWithSee,
  isHomiProposalAction,
  type HomiProposalAction,
  type HomiRequestEnvelope,
  type AttachmentReference,
  type SeeResult,
} from './homiContract';
import { sendMessage as sendMessageWithAttachments } from './homiAttachments';

export type HomiClientInput = {
  text: string;
  accessToken: string;
  actorId: string;
  householdId: string;
  conversationId: string;
  signal?: AbortSignal | null;
  contextScope?: string | null;
  attachments?: AttachmentReference[];
  proposalAction?: HomiProposalAction;
  turnId?: string;
};

export type HomiClientResult = {
  answer: string;
  decisionKind: 'direct_response' | 'clarify' | 'tool_request' | 'action_proposal' | 'action_executed' | 'blocked';
  grounded?: boolean;
  truncated?: boolean;
  proposal?: unknown;
  seeResults?: SeeResult[];
  conversationId: string;
  turnId: string;
};

const CONVERSATION_ID_RE = /^conv_[A-Za-z0-9_-]{8,64}$/;

export async function invokeHomi(input: HomiClientInput): Promise<HomiClientResult> {
  const text = input.text?.trim?.() ?? '';
  const hasProposalAction = input.proposalAction !== undefined;

  if (hasProposalAction && !isHomiProposalAction(input.proposalAction)) {
    throw new ApiError(
      'La acción de propuesta no es válida.',
      0,
      'homi_invalid_proposal_action',
    );
  }

  const proposalAction = input.proposalAction;
  if (!text && (!input.attachments || input.attachments.length === 0) && !hasProposalAction) {
    throw new ApiError('El mensaje no puede estar vacío.', 0, 'homi_empty_text');
  }
  if (!input.accessToken) {
    throw new ApiError('Sesión no disponible.', 0, 'homi_missing_access_token');
  }
  if (!input.actorId) {
    throw new ApiError('Actor no disponible.', 0, 'homi_missing_actor_id');
  }
  if (!input.householdId) {
    throw new ApiError('Hogar no disponible.', 0, 'homi_missing_household_id');
  }
  if (!CONVERSATION_ID_RE.test(input.conversationId)) {
    throw new ApiError('Conversación inválida.', 0, 'homi_invalid_conversation_id');
  }

  const turnId = input.turnId ?? `turn_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;

  const result = await sendMessageWithAttachments({
    conversationId: input.conversationId,
    turnId,
    text,
    attachments: input.attachments,
    proposalAction: input.proposalAction,
    householdId: input.householdId,
    actorId: input.actorId,
    accessToken: input.accessToken,
    signal: input.signal,
    contextScope: input.contextScope,
  });

  return {
    answer: result.answer,
    decisionKind: result.decision_kind as HomiClientResult['decisionKind'],
    proposal: result.proposal,
    grounded: result.grounded,
    truncated: result.truncated,
    seeResults: result.see_results,
    conversationId: result.conversation_id,
    turnId: result.turn_id,
  };
}

export const homiClient = { invoke: invokeHomi };
export const invoke = invokeHomi;
export const sendHomiMessage = invokeHomi;
export default invokeHomi;
