/**
 * HOMI V1 — Manual dictation transport.
 *
 * Decision de producto (Actor A): Turn Talking / T31 cancelado. La voz V1 es
 * grabacion manual -> STT -> borrador editable -> envio manual de texto.
 *
 * Este transporte reutiliza la grabacion nativa que ya funciono fisicamente en
 * iPhone (T30): `expo-audio` AudioRecorder + RecordingPresets.HIGH_QUALITY.
 *
 * NO hay escucha continua, VAD, endpointing, barge-in, TTS ni LiveKit.
 * El audio se envia EXCLUSIVAMENTE al endpoint STT-only; la respuesta no
 * dispara THINK, tools ni reproduccion de audio.
 */

import {
  AudioModule,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  setIsAudioActiveAsync,
} from 'expo-audio';
import { File } from 'expo-file-system';

import { transcribeAudio } from '../../services/homi/homiDictation';
import { HomiVoiceError } from './homiVoiceTransport';
import type {
  HomiVoiceAnswer,
  HomiVoiceCapture,
  HomiVoiceTransport,
  HomiVoiceTransportKind,
} from './homiVoiceTransport';

export type ExpoManualDictationDeps = {
  /** Token de sesion de Supabase; la identidad resuelve SERVER SIDE en T07. */
  accessToken: string;
};

type Recorder = InstanceType<typeof AudioModule.AudioRecorder>;

const MAX_RECORDING_S = 120;

/**
 * Expo Go only ships the native modules included in the store client. When
 * `expo-audio` is missing, the native call rejects with a raw `not_found`
 * string. Translate it without pretending the module exists.
 */
const nativeAudioError = (action: string, error: unknown): HomiVoiceError => {
  const raw = error instanceof Error ? error.message : String(error ?? '');
  const missingModule =
    /not_found|cannot find module|native module|does not respond|null is not an object/i.test(raw);
  const message = missingModule
    ? `El cliente no incluye el módulo nativo de audio (expo-audio) necesario para ${action}. Usá un cliente Expo Go con SDK 58 que incluya ese módulo.`
    : `No se pudo ${action}: ${raw}`;
  return new HomiVoiceError('unsupported', message, false);
};

export class ExpoManualDictationTransport implements HomiVoiceTransport {
  readonly kind: HomiVoiceTransportKind = 'expo-go-dictation';
  readonly available = true;
  readonly unavailableReason = null;

  private recorder: Recorder | null = null;
  private recordingStartedAt: number | null = null;
  private deps: ExpoManualDictationDeps;

  constructor(deps: ExpoManualDictationDeps) {
    this.deps = deps;
  }

  async initialize(): Promise<void> {
    // The microphone is NOT activated here: only when the user taps grabar.
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        allowsRecording: false,
        interruptionMode: 'doNotMix',
      });
      await setIsAudioActiveAsync(false);
    } catch (error) {
      throw nativeAudioError('configurar el modo de audio', error);
    }
  }

  async startCapture(): Promise<void> {
    if (this.recorder) {
      await this.cancelCapture();
    }

    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      throw new HomiVoiceError(
        'permission_denied',
        'Homi necesita permiso de micrófono para transcribir lo que digas.',
      );
    }

    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        allowsRecording: true,
        interruptionMode: 'doNotMix',
      });
      await setIsAudioActiveAsync(true);

      // expo-audio applies `createRecordingOptions()` inside
      // prepareToRecordAsync(options). Passing the nested preset to the
      // @hidden AudioRecorder constructor bypasses that transformation, so
      // the iOS fields of HIGH_QUALITY (.m4a/AAC/44.1 kHz) never reach native.
      const AudioRecorder = Reflect.get(AudioModule, 'AudioRecorder') as typeof AudioModule.AudioRecorder;
      this.recorder = new AudioRecorder({});
      await this.recorder.prepareToRecordAsync(RecordingPresets.HIGH_QUALITY);
      this.recorder.record();
    } catch (error) {
      await this.cancelCapture();
      throw nativeAudioError('iniciar la grabación', error);
    }
    this.recordingStartedAt = Date.now();
  }

  async stopCapture(): Promise<HomiVoiceCapture> {
    const recorder = this.recorder;
    if (!recorder) {
      throw new HomiVoiceError('record_failed', 'No hay ninguna grabación activa.');
    }

    await recorder.stop();
    this.recorder = null;

    const durationS = this.recordingStartedAt
      ? (Date.now() - this.recordingStartedAt) / 1000
      : null;
    this.recordingStartedAt = null;

    await this.deactivateAudio();

    const uri = recorder.uri ?? null;
    if (!uri) {
      throw new HomiVoiceError('record_failed', 'La grabación no produjo ningún archivo.');
    }

    if (durationS !== null && durationS > MAX_RECORDING_S) {
      await this.deleteRecording(uri);
      throw new HomiVoiceError(
        'record_failed',
        'La grabación supera el límite de dos minutos. Probá con una más corta.',
      );
    }

    return {
      uri,
      mimeType: 'audio/mp4',
      fileName: 'homi-dictation.m4a',
      durationS,
    };
  }

  async cancelCapture(): Promise<void> {
    const recorder = this.recorder;
    const uri = recorder?.uri ?? null;
    this.recorder = null;
    this.recordingStartedAt = null;

    if (recorder) {
      try {
        await recorder.stop();
      } catch {
        // The recorder may already be stopped.
      }
    }
    if (uri) {
      await this.deleteRecording(uri);
    }
    await this.deactivateAudio();
  }

  /**
   * Deliver the captured audio to the STT-only endpoint. The returned answer
   * carries ONLY the transcript: `answer` is empty on purpose so no caller can
   * accidentally render a spoken answer or start a playback.
   */
  async deliverTurn(capture: HomiVoiceCapture): Promise<HomiVoiceAnswer> {
    if (!capture.uri) {
      throw new HomiVoiceError('upload_failed', 'No hay audio para transcribir.');
    }

    let result;
    try {
      result = await transcribeAudio({
        file: { uri: capture.uri, name: capture.fileName, type: capture.mimeType },
        accessToken: this.deps.accessToken,
      });
    } catch (error) {
      throw new HomiVoiceError(
        'upload_failed',
        error instanceof Error ? error.message : 'No se pudo transcribir el audio.',
      );
    } finally {
      // The native file is no longer needed once the request settles, whether
      // it succeeded, was cancelled or failed.
      await this.deleteRecording(capture.uri);
    }

    return {
      transcript: result.transcript,
      answer: '',
      spokenText: '',
      turnId: null,
      conversationId: null,
      audioId: null,
      audioFormat: null,
      sampleRate: null,
      durationS: result.duration_s,
      decisionKind: null,
      generationId: null,
      turnVersion: null,
      speechStatus: null,
    };
  }

  /** HOMI V1 has no TTS: playback is a deliberate no-op. */
  async playAnswer(): Promise<void> {
    return;
  }

  async stopPlayback(): Promise<void> {
    return;
  }

  /** Recover in place after a failure: no need to leave HOMI. */
  async recover(): Promise<void> {
    await this.cancelCapture();
    await this.initialize();
  }

  async release(): Promise<void> {
    await this.cancelCapture();
  }

  private async deactivateAudio(): Promise<void> {
    try {
      await setIsAudioActiveAsync(false);
      await setAudioModeAsync({
        playsInSilentMode: true,
        allowsRecording: false,
        interruptionMode: 'doNotMix',
      });
    } catch {
      // Best effort: the textual channel stays available regardless.
    }
  }

  private async deleteRecording(uri: string): Promise<void> {
    try {
      const file = new File(uri);
      if (file.exists) {
        file.delete();
      }
    } catch {
      // Best effort cleanup of the temporary recording.
    }
  }
}
