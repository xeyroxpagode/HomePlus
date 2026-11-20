/**
 * T30 - Common voice transport contract.
 *
 * Both transports (LiveKit native for development builds, and the Expo Go
 * turn based transport) implement exactly this contract, so HomiSurface and
 * HomiComposer never know which one is active.
 *
 * Responsibilities of a transport:
 *   - initialize
 *   - start capturing the user voice
 *   - stop capturing and deliver the turn
 *   - receive the authorized semantic answer
 *   - play the answer audio
 *   - cancel the current operation
 *   - release every resource
 *   - report the real state and the real errors
 */

export type HomiVoiceState =
  | 'idle'
  | 'recording'
  | 'uploading'
  | 'listening'
  | 'detecting_voice'
  | 'processing'
  | 'speaking'
  | 'interrupted'
  | 'error';

/** T31 — voice activity emitted by the realtime transport (VAD owner HOMI-C). */
export type HomiVoiceActivity =
  | { type: 'voice_start'; at: number; rms?: number }
  | { type: 'voice_end'; at: number; rms?: number; text?: string }
  | { type: 'barge_in'; at: number; rms?: number }
  | {
      type: 'speech_start';
      at: number;
      generationId?: string | null;
      turnId?: string | null;
    }
  | {
      type: 'speech_end';
      at: number;
      generationId?: string | null;
      deliveredS?: number;
      interrupted?: boolean;
    }
  /** The semantic answer is ready; the surface inserts the chat messages. */
  | { type: 'answer'; at: number; answer: HomiVoiceAnswer }
  /** A recoverable voice failure: the surface must reset, not leave HOMI. */
  | {
      type: 'voice_error';
      at: number;
      code: string;
      message: string;
      generationId?: string | null;
      turnId?: string | null;
    };

export type HomiVoiceErrorCode =
  | 'permission_denied'
  | 'record_failed'
  | 'upload_failed'
  | 'turn_failed'
  | 'playback_failed'
  | 'playback_timeout'
  | 'unsupported';

export class HomiVoiceError extends Error {
  readonly code: HomiVoiceErrorCode;
  readonly recoverable: boolean;

  constructor(code: HomiVoiceErrorCode, message: string, recoverable = true) {
    super(message);
    this.name = 'HomiVoiceError';
    this.code = code;
    this.recoverable = recoverable;
  }
}

/** A captured user turn, ready to be delivered to HOMI-D. */
export type HomiVoiceCapture = {
  /** Local file URI of the recording, when the transport produces a file. */
  uri: string | null;
  /** MIME type of the recording. */
  mimeType: string;
  /** File name hint (with extension) used by the server for format detection. */
  fileName: string;
  /** Duration in seconds when the transport can report it. */
  durationS: number | null;
};

/** The authorized semantic answer returned by HOMI-D. */
export type HomiVoiceAnswer = {
  transcript: string;
  answer: string;
  spokenText: string;
  turnId: string | null;
  conversationId: string | null;
  /** Opaque id of the answer audio, downloadable through an authenticated route. */
  audioId: string | null;
  audioFormat: string | null;
  sampleRate: number | null;
  durationS: number | null;
  decisionKind: string | null;
  /** T31 — authoritative generation/turn id echoed by HOMI-D. */
  generationId?: string | null;
  turnVersion?: number | null;
  speechStatus?: string | null;
};

export type HomiVoiceTransportKind =
  | 'livekit-native'
  | 'expo-go-turns'
  /** Expo Go SDK 58: PCM stream + client VAD + authenticated HTTP turns. */
  | 'expo-go-stream'
  /** HOMI V1: grabacion manual + STT-only. Sin VAD, barge-in ni TTS. */
  | 'expo-go-dictation';

export interface HomiVoiceTransport {
  readonly kind: HomiVoiceTransportKind;
  /** True when the transport can run on this runtime. */
  readonly available: boolean;
  /** Human readable reason when the transport is not available. */
  readonly unavailableReason: string | null;

  initialize(): Promise<void>;
  startCapture(): Promise<void>;
  stopCapture(): Promise<HomiVoiceCapture>;
  cancelCapture(): Promise<void>;
  /** Deliver the captured turn and resolve with the authorized answer. */
  deliverTurn(capture: HomiVoiceCapture): Promise<HomiVoiceAnswer>;
  /** Play the answer audio. Resolves when the playback finished or failed. */
  playAnswer(
    answer: HomiVoiceAnswer,
    expectedGenerationId?: string | null,
  ): Promise<void>;
  stopPlayback(): Promise<void>;
  release(): Promise<void>;

  /** T31 — optional realtime hooks. HTTP transports keep the manual button. */
  setVoiceActivityListener?(listener: (event: HomiVoiceActivity) => void): void;
  beginTurn?(
    conversationId: string,
    turnId: string,
  ): Promise<{ generationId: string; turnId: string; turnVersion: number }>;
  interruptGeneration?(conversationId: string, generationId: string): Promise<void>;
  reportDelivery?(input: {
    conversationId: string;
    generationId: string;
    deliveredS: number;
    interrupted: boolean;
  }): Promise<void>;
  /** Reset audio/turn resources in place after a failure. */
  recover?(): Promise<void>;
}
