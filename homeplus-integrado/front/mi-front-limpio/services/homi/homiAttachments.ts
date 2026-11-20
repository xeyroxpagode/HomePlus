import { requestJson, OPERATION_KINDS, ApiError, AbortError, getBearerHeaders } from '../api';
import {
  HOMI_CONTRACT_VERSION,
  isHomiResponseEnvelopeWithSee,
  isHomiSuccessEnvelopeWithSee,
  type AttachmentUploadResult,
  type AttachmentReference,
  type HomiProposalAction,
  type SeeResult,
} from './homiContract';
import {
  MultipartTransportError,
  postMultipartText,
} from './homiMultipart';

const RAW_API_BASE_URL = process.env.EXPO_PUBLIC_API_URL;

/**
 * T07 - Homi gateway base URL.
 *
 * Todo el trafico de Homi (texto, voz y adjuntos) atraviesa el gateway
 * autenticado del backend T07. El cliente NUNCA llama directamente a HOMI-D:
 * el gateway resuelve la identidad y el household SERVER SIDE desde el bearer
 * token, por lo que el telefono nunca elige su propia identidad.
 */
const resolveApiBaseUrl = (): string | null => {
  if (!RAW_API_BASE_URL) return null;
  return RAW_API_BASE_URL.replace(/\/+$/, '');
};

const API_BASE_URL = resolveApiBaseUrl();

export const HOMI_CONFIGURED = Boolean(API_BASE_URL);

const buildHomiUrl = (path: string): string => {
  if (!API_BASE_URL) {
    throw new ApiError(
      'Falta EXPO_PUBLIC_API_URL para conectar con el gateway de Homi.',
      0,
      'homi_url_missing',
    );
  }
  const base = API_BASE_URL.replace(/\/+$/, '');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
};

/**
 * Upload a file to HOMI-D and return the opaque attachment_id.
 * Uses the native multipart transport (not requestJson, which is JSON-only).
 */
export const uploadAttachment = async ({
  file,
  householdId,
  actorId,
  accessToken,
  conversationId,
  declaredMime,
  signal,
}: {
  file: { uri: string; name: string; type: string };
  householdId: string;
  actorId: string;
  accessToken: string;
  conversationId?: string;
  declaredMime?: string;
  signal?: AbortSignal | null;
}): Promise<AttachmentUploadResult> => {
  const formData = new FormData();
  // React Native / Expo: attach file with name, type, and URI
  formData.append('file', {
    uri: file.uri,
    name: file.name,
    type: file.type,
  } as any);
  if (conversationId) {
    formData.append('conversation_id', conversationId);
  }
  if (declaredMime) {
    formData.append('declared_mime', declaredMime);
  }

  const headers = {
    Authorization: `Bearer ${accessToken}`,
    'X-Household-Id': householdId,
    'X-Actor-Id': actorId,
    // Content-Type intentionally omitted: native XHR sets the boundary.
  };

  try {
    const response = await postMultipartText({
      url: buildHomiUrl('/api/homi/v1/attachments/upload'),
      body: formData,
      headers,
      signal,
      // SEE document processing (PDF/docling) can exceed a minute. Match the
      // gateway/orchestrator budget so the client does not abandon first.
      timeoutMs: 180000,
    });

    const text = response.text;
    let payload: unknown = null;
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      throw new ApiError(
        'Respuesta invÃ¡lida del servidor de adjuntos.',
        response.status,
        'homi_invalid_response',
      );
    }

    if (!response.ok) {
      const code = (payload as Record<string, unknown> | undefined)?.detail
        ? String((payload as Record<string, unknown>).detail)
        : null;
      throw new ApiError(
        code || 'No se pudo subir el adjunto.',
        response.status,
        code ?? 'homi_upload_error',
      );
    }

    return payload as AttachmentUploadResult;
  } catch (error) {
    if (error instanceof MultipartTransportError) {
      if (error.code === 'aborted') {
        throw new AbortError('/api/homi/v1/attachments/upload', signal ?? undefined);
      }
      if (error.code === 'timeout') {
        throw new ApiError(
          'La carga del adjunto excediÃ³ el tiempo lÃ­mite.',
          0,
          'homi_request_timeout',
        );
      }
      throw new ApiError(
        'No se pudo conectar con el servidor de adjuntos.',
        0,
        'homi_network_error',
      );
    }
    if (error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')) {
      throw new AbortError('/api/homi/v1/attachments/upload', signal ?? undefined);
    }
    throw error;
  }
};

/**
 * Delete an attachment before sending (user regret).
 */
export const deleteAttachment = async ({
  attachmentId,
  householdId,
  actorId,
  accessToken,
  signal,
}: {
  attachmentId: string;
  householdId: string;
  actorId: string;
  accessToken: string;
  signal?: AbortSignal | null;
}): Promise<boolean> => {
  const headers = {
    ...getBearerHeaders(accessToken),
    'X-Household-Id': householdId,
    'X-Actor-Id': actorId,
    'Content-Type': 'application/json',
  };

  const controller = new AbortController();
  const effectiveSignal = signal ?? undefined;
  if (effectiveSignal) {
    if (effectiveSignal.aborted) {
      throw new AbortError(`/api/homi/v1/attachments/${attachmentId}`, effectiveSignal);
    }
    effectiveSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  const timeoutId = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(buildHomiUrl(`/api/homi/v1/attachments/${attachmentId}`), {
      method: 'DELETE',
      headers,
      signal: effectiveSignal,
    });

    clearTimeout(timeoutId);
    if (response.status === 404) return false;
    if (!response.ok) {
      throw new ApiError(
        'No se pudo eliminar el adjunto.',
        response.status,
        'homi_delete_error',
      );
    }
    return true;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')) {
      throw new AbortError(`/api/homi/v1/attachments/${attachmentId}`, effectiveSignal);
    }
    throw error;
  }
};

/**
 * Get attachment metadata (optional, for preview/verification).
 */
export const getAttachment = async ({
  attachmentId,
  householdId,
  actorId,
  accessToken,
  signal,
}: {
  attachmentId: string;
  householdId: string;
  actorId: string;
  accessToken: string;
  signal?: AbortSignal | null;
}): Promise<AttachmentUploadResult | null> => {
  const headers = {
    ...getBearerHeaders(accessToken),
    'X-Household-Id': householdId,
    'X-Actor-Id': actorId,
    Accept: 'application/json',
  };

  const controller = new AbortController();
  const effectiveSignal = signal ?? undefined;
  if (effectiveSignal) {
    if (effectiveSignal.aborted) {
      throw new AbortError(`/api/homi/v1/attachments/${attachmentId}`, effectiveSignal);
    }
    effectiveSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  const timeoutId = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(buildHomiUrl(`/api/homi/v1/attachments/${attachmentId}`), {
      method: 'GET',
      headers,
      signal: effectiveSignal,
    });

    clearTimeout(timeoutId);
    if (response.status === 404) return null;
    if (!response.ok) {
      throw new ApiError(
        'No se pudo obtener el adjunto.',
        response.status,
        'homi_get_attachment_error',
      );
    }

    const text = await response.text();
    const payload = JSON.parse(text) as unknown;
    return payload as AttachmentUploadResult;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')) {
      throw new AbortError(`/api/homi/v1/attachments/${attachmentId}`, effectiveSignal);
    }
    throw error;
  }
};

/**
 * Health check for HOMI-D availability.
 */
export const homiHealthCheck = async (): Promise<boolean> => {
  if (!API_BASE_URL) return false;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    return false;
  }
};

/**
 * Send a turn to HOMI-D with text and optional attachments.
 * Uses the existing requestJson infrastructure with the canonical contract.
 */
export const sendMessage = async ({
  conversationId,
  turnId,
  text,
  attachments,
  proposalAction,
  householdId,
  actorId,
  accessToken,
  signal,
  contextScope,
}: {
  conversationId: string;
  turnId: string;
  text: string;
  attachments?: AttachmentReference[];
  proposalAction?: HomiProposalAction;
  householdId: string;
  actorId: string;
  accessToken: string;
  signal?: AbortSignal | null;
  contextScope?: string | null;
}): Promise<{
  answer: string;
  decision_kind: string;
  grounded?: boolean;
  truncated?: boolean;
  proposal?: unknown;
  result?: unknown;
  status?: string;
  error?: unknown;
  see_results?: SeeResult[];
  conversation_id: string;
  turn_id: string;
}> => {
  const payload: Record<string, unknown> = {
    text,
    conversation_id: conversationId,
    turn_id: turnId,
  };
  if (attachments && attachments.length > 0) {
    payload.attachments = attachments;
  }
  if (proposalAction) {
    payload.proposal_action = proposalAction;
  }

  const response = await requestJson<unknown>('/api/homi/v1/text/turn', {
    method: 'POST',
    accessToken,
    body: payload,
    operationKind: OPERATION_KINDS.NON_VERSIONED_MUTATION,
    signal,
    contextScope,
    timeoutMs: 120000,
  });

  if (!isHomiResponseEnvelopeWithSee(response)) {
    throw new ApiError('Respuesta invÃ¡lida de Homi.', 0, 'homi_invalid_response');
  }

  if (!isHomiSuccessEnvelopeWithSee(response)) {
    // Error envelope - ApiError is thrown by requestJson for non-ok responses
    throw new ApiError('Error del orquestador HOMI-D.', 0, 'homi_error_envelope');
  }

  const result = response.result;
  const correlation = response.correlation;

  return {
    answer: result.answer,
    decision_kind: result.decision_kind,
    grounded: result.decision_kind === 'tool_request' ? result.grounded : undefined,
    truncated: result.decision_kind === 'tool_request' ? result.truncated : undefined,
    proposal: (result as { proposal?: unknown }).proposal,
    result: (result as { result?: unknown }).result,
    status: (result as { status?: string }).status,
    error: (result as { error?: unknown }).error,
    see_results: result.see_results,
    conversation_id: correlation?.conversation_id ?? conversationId,
    turn_id: correlation?.turn_id ?? turnId,
  };
};

/**
 * T30 - Voice turn: real audio -> HOMI-D -> STT (HOMI-C) -> THINK (HOMI-A)
 * -> tools / policy -> SPEAK (HOMI-C) -> answer audio id.
 *
 * The audio is uploaded as multipart/form-data. HOMI-D performs the single
 * STT inference, the single semantic turn and the single synthesis.
 */
export const sendVoiceTurn = async ({
  file,
  conversationId,
  turnId,
  householdId,
  actorId,
  accessToken,
  requestId,
  generationId,
  signal,
}: {
  file: { uri: string; name: string; type: string };
  conversationId: string;
  turnId: string;
  householdId: string;
  actorId: string;
  accessToken: string;
  requestId?: string | null;
  /** T31 â€” generation id emitted by HOMI-D, echoed back for stale-audio guard. */
  generationId?: string | null;
  signal?: AbortSignal | null;
}): Promise<{
  request_id: string;
  status: string;
  transcript: string;
  answer: string;
  spoken_text: string;
  display_text: string;
  decision_kind: string | null;
  turn_id: string;
  conversation_id: string;
  audio_id: string | null;
  audio_format: string | null;
  sample_rate: number | null;
  duration_s: number | null;
  generation_id?: string | null;
  turn_version?: number | null;
  speech_status?: string | null;
}> => {
  const formData = new FormData();
  formData.append('file', {
    uri: file.uri,
    name: file.name,
    type: file.type,
  } as any);
  formData.append('conversation_id', conversationId);
  formData.append('turn_id', turnId);
  if (requestId) {
    formData.append('x_request_id', requestId);
  }
  if (generationId) {
    formData.append('generation_id', generationId);
  }

  try {
    const response = await postMultipartText({
      url: buildHomiUrl('/api/homi/voice/turn'),
      body: formData,
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      signal,
      timeoutMs: 180000,
    });

    const text = response.text;
    let payload: any = null;
    try {
      payload = JSON.parse(text);
    } catch {
      throw new ApiError(
        'Respuesta invÃ¡lida del servidor de voz.',
        response.status,
        'homi_voice_invalid_response',
      );
    }

    if (!response.ok) {
      const code = payload?.error?.code || payload?.detail || null;
      throw new ApiError(
        code ? String(code) : 'No se pudo procesar el turno de voz.',
        response.status,
        code ? String(code) : 'homi_voice_error',
      );
    }

    return payload;
  } catch (error) {
    if (error instanceof MultipartTransportError) {
      if (error.code === 'aborted') {
        throw new AbortError('/api/homi/voice/turn', signal ?? undefined);
      }
      if (error.code === 'timeout') {
        throw new ApiError(
          'El turno de voz excediÃ³ el tiempo lÃ­mite.',
          0,
          'homi_request_timeout',
        );
      }
      throw new ApiError(
        'No se pudo conectar con el servidor de voz.',
        0,
        'homi_network_error',
      );
    }
    if (error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')) {
      throw new AbortError('/api/homi/voice/turn', signal ?? undefined);
    }
    throw error;
  }
};

/**
 * Download the generated answer audio through the authenticated gateway.
 */
export const downloadVoiceAudio = async ({
  audioId,
  householdId,
  actorId,
  accessToken,
  signal,
}: {
  audioId: string;
  householdId: string;
  actorId: string;
  accessToken: string;
  signal?: AbortSignal | null;
}): Promise<Blob> => {
  const controller = new AbortController();
  const effectiveSignal = signal ?? undefined;
  if (effectiveSignal) {
    if (effectiveSignal.aborted) {
      throw new AbortError(`/api/homi/voice/audio/${audioId}`, effectiveSignal);
    }
    effectiveSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  const timeoutId = setTimeout(() => controller.abort(), 60000);

  try {
    const response = await fetch(buildHomiUrl(`/api/homi/voice/audio/${audioId}`), {
      method: 'GET',
      headers: {
        ...getBearerHeaders(accessToken),
      },
      signal: effectiveSignal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new ApiError(
        'No se pudo descargar el audio de la respuesta.',
        response.status,
        'homi_voice_audio_error',
      );
    }

    return await response.blob();
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')) {
      throw new AbortError(`/api/homi/voice/audio/${audioId}`, effectiveSignal);
    }
    throw error;
  }
};

/**
 * T31 â€” Voice turn control over the authenticated gateway.
 *
 * The client never chooses actor or household: the T07 gateway derives both
 * from the bearer token and forwards the control to HOMI-D.
 */
const sendVoiceControl = async (
  path: string,
  body: Record<string, unknown>,
  accessToken: string,
): Promise<Record<string, unknown>> => {
  const response = await fetch(buildHomiUrl(`/api/homi/voice/${path}`), {
    method: 'POST',
    headers: {
      ...getBearerHeaders(accessToken),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  let payload: Record<string, unknown> | null = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload?.error ?? payload?.detail ?? `homi_voice_control_${response.status}`;
    throw new ApiError(
      `No se pudo completar el control de voz (${String(detail)}).`,
      response.status,
      'homi_voice_control_error',
    );
  }
  return payload ?? {};
};

export const beginVoiceTurn = async ({
  conversationId,
  turnId,
  accessToken,
}: {
  conversationId: string;
  turnId: string;
  accessToken: string;
}): Promise<{
  generation_id: string;
  turn_id: string;
  turn_version: number;
}> => {
  const payload = await sendVoiceControl(
    'turn/begin',
    { conversation_id: conversationId, turn_id: turnId },
    accessToken,
  );
  return {
    generation_id: String(payload.generation_id ?? ''),
    turn_id: String(payload.turn_id ?? turnId),
    turn_version: Number(payload.turn_version ?? 0),
  };
};

export const sendPartialTranscript = async ({
  conversationId,
  turnId,
  text,
  accessToken,
}: {
  conversationId: string;
  turnId: string;
  text: string;
  accessToken: string;
}): Promise<void> => {
  await sendVoiceControl(
    'transcript/partial',
    { conversation_id: conversationId, turn_id: turnId, text },
    accessToken,
  );
};

/** Barge-in: invalidate a generation. Never touches tools or proposals. */
export const interruptVoiceGeneration = async ({
  conversationId,
  generationId,
  accessToken,
}: {
  conversationId: string;
  generationId: string;
  accessToken: string;
}): Promise<void> => {
  await sendVoiceControl(
    'interrupt',
    { conversation_id: conversationId, generation_id: generationId },
    accessToken,
  );
};

export const reportVoiceDelivery = async ({
  conversationId,
  generationId,
  deliveredS,
  interrupted,
  accessToken,
}: {
  conversationId: string;
  generationId: string;
  deliveredS: number;
  interrupted: boolean;
  accessToken: string;
}): Promise<void> => {
  await sendVoiceControl(
    'delivery',
    {
      conversation_id: conversationId,
      generation_id: generationId,
      delivered_s: Math.max(0, deliveredS),
      interrupted: interrupted === true,
    },
    accessToken,
  );
};

export const homiAttachmentsClient = {
  upload: uploadAttachment,
  delete: deleteAttachment,
  get: getAttachment,
  healthCheck: homiHealthCheck,
  sendMessage,
  sendVoiceTurn,
  downloadVoiceAudio,
  beginVoiceTurn,
  sendPartialTranscript,
  interruptVoiceGeneration,
  reportVoiceDelivery,
};

