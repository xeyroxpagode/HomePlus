import { ApiError, AbortError, getBearerHeaders } from '../api';
import {
  MultipartTransportError,
  postMultipartText,
} from './homiMultipart';

const RAW_API_BASE_URL = process.env.EXPO_PUBLIC_API_URL;

const resolveApiBaseUrl = (): string | null => {
  if (!RAW_API_BASE_URL) return null;
  return RAW_API_BASE_URL.replace(/\/+$/, '');
};

const API_BASE_URL = resolveApiBaseUrl();

export const HOMI_DICTATION_CONFIGURED = Boolean(API_BASE_URL);

const buildHomiUrl = (path: string): string => {
  if (!API_BASE_URL) {
    throw new ApiError(
      'Falta EXPO_PUBLIC_API_URL para conectar con el gateway de Homi.',
      0,
      'homi_url_missing',
    );
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
};

export type HomiTranscriptionResult = {
  status: string;
  /** Texto reconocido. Todavía NO es un mensaje: es un borrador editable. */
  transcript: string;
  request_id: string | null;
  stt: {
    engine?: string | null;
    model?: string | null;
    duration_s?: number | null;
  } | null;
  duration_s: number | null;
  /** Garantías del contrato STT-only, verificadas en el gateway. */
  semantic_turn: false;
  tools_executed: false;
  tts_generated: false;
};

/**
 * HOMI V1 — dictado manual: audio autenticado -> STT real -> SOLO texto.
 *
 * Este servicio NO llama a `/api/homi/voice/turn` (que encadenaba
 * STT -> THINK -> TTS). El gateway devuelve exclusivamente la transcripción:
 * no crea turno semántico, no ejecuta herramientas y no genera audio.
 * La edición del borrador y el envío manual ocurren en la UI.
 */
export const transcribeAudio = async ({
  file,
  accessToken,
  requestId,
  signal,
}: {
  file: { uri: string; name: string; type: string };
  accessToken: string;
  requestId?: string | null;
  signal?: AbortSignal | null;
}): Promise<HomiTranscriptionResult> => {
  const formData = new FormData();
  formData.append('file', {
    uri: file.uri,
    name: file.name,
    type: file.type,
  } as any);
  if (requestId) {
    formData.append('x_request_id', requestId);
  }

  try {
    const response = await postMultipartText({
      url: buildHomiUrl('/api/homi/v1/voice/transcript'),
      body: formData,
      headers: {
        ...getBearerHeaders(accessToken),
      },
      signal,
      timeoutMs: 120000,
    });

    let payload: any = null;
    try {
      payload = JSON.parse(response.text);
    } catch {
      throw new ApiError(
        'Respuesta inválida del servicio de transcripción.',
        response.status,
        'homi_transcript_invalid_response',
      );
    }

    if (!response.ok) {
      const code = payload?.error?.code || payload?.detail || null;
      throw new ApiError(
        code ? String(code) : 'No se pudo transcribir el audio.',
        response.status,
        code ? String(code) : 'homi_transcript_error',
      );
    }

    if (typeof payload?.transcript !== 'string') {
      throw new ApiError(
        'El servicio de transcripción no devolvió texto.',
        0,
        'homi_transcript_missing',
      );
    }

    return {
      status: payload.status ?? 'ok',
      transcript: payload.transcript,
      request_id: payload.request_id ?? null,
      stt: payload.stt ?? null,
      duration_s: payload.duration_s ?? null,
      semantic_turn: false,
      tools_executed: false,
      tts_generated: false,
    };
  } catch (error) {
    if (error instanceof MultipartTransportError) {
      if (error.code === 'aborted') {
        throw new AbortError('/api/homi/v1/voice/transcript', signal ?? undefined);
      }
      if (error.code === 'timeout') {
        throw new ApiError(
          'La transcripción excedió el tiempo límite. Probá de nuevo.',
          0,
          'homi_request_timeout',
        );
      }
      throw new ApiError(
        'No se pudo conectar con el servicio de transcripción.',
        0,
        'homi_network_error',
      );
    }
    if (error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')) {
      throw new AbortError('/api/homi/v1/voice/transcript', signal ?? undefined);
    }
    throw error;
  }
};
