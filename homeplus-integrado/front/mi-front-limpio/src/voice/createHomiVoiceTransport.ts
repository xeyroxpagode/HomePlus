/**
 * HOMI V1 — Voice transport factory.
 *
 * Product decision (Actor A): Turn Talking / T31 is CANCELLED. HOMI V1 has
 * exactly one voice path:
 *
 *   manual recording -> STT-only transcript -> editable draft -> manual send
 *
 * The T31 streaming/VAD and native realtime transports are NOT imported here.
 * They stop being a dependency of the V1 voice experience. Their code is
 * preserved as historical infrastructure; it is not deleted.
 */

import Constants, { ExecutionEnvironment } from 'expo-constants';

import { ExpoManualDictationTransport } from './expoManualDictationTransport';
import type { ExpoManualDictationDeps } from './expoManualDictationTransport';
import type { HomiVoiceTransport } from './homiVoiceTransport';

/** Diagnostic only: the V1 factory no longer selects transports by runtime. */
export const isExpoGoRuntime = (): boolean => {
  try {
    return Constants.executionEnvironment === ExecutionEnvironment.StoreClient;
  } catch {
    return false;
  }
};

export type VoiceTransportFactoryDeps = ExpoManualDictationDeps;

/**
 * The single supported V1 transport: manual capture, STT-only delivery,
 * no continuous listening, no VAD, no barge-in, no TTS and no LiveKit.
 */
export const createHomiVoiceTransport = async (
  deps: VoiceTransportFactoryDeps,
): Promise<HomiVoiceTransport> => new ExpoManualDictationTransport(deps);
