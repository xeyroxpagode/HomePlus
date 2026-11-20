'use strict';

/**
 * HOMI V1 — voice simplification contract (Actor A decision).
 *
 * This reads the REAL sources and asserts the boundaries of the approved
 * architecture: manual dictation -> STT-only -> editable draft -> text send.
 * T31 / Turn Talking must not be a dependency of the V1 voice path.
 * It is a deterministic contract test, not a device test.
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const read = (relativePath) =>
  fs.readFileSync(path.join(__dirname, '..', relativePath), 'utf8');

const factory = read('src/voice/createHomiVoiceTransport.ts');
const transport = read('src/voice/expoManualDictationTransport.ts');
const dictation = read('services/homi/homiDictation.ts');
const surface = read('components/homi/HomiSurface.tsx');
const composer = read('components/homi/HomiComposer.tsx');

test('the V1 factory selects only the manual dictation transport', () => {
  assert.match(factory, /ExpoManualDictationTransport/);
  // Check real imports/calls, not the historical comment that names them.
  assert.doesNotMatch(factory, /from '\.\/expoStreamVoiceTransport'/);
  assert.doesNotMatch(factory, /import\('\.\/expoStreamVoiceTransport'\)/);
  assert.doesNotMatch(factory, /livekitVoiceTransport'/);
  assert.doesNotMatch(factory, /homiLiveKit'/);
  assert.doesNotMatch(factory, /(createIosExpoGoTransport|createRealtimeVoiceTransport|isRealtimeVoiceEnabled)\s*=/);
});

test('the manual transport has no VAD, barge-in, TTS or coupled turn', () => {
  assert.match(transport, /requestRecordingPermissionsAsync/);
  assert.match(transport, /RecordingPresets\.HIGH_QUALITY/);
  assert.match(transport, /transcribeAudio/);
  assert.match(transport, /async release\(\)/);
  assert.match(transport, /deactivateAudio/);
  assert.match(transport, /deleteRecording/);
  for (const removed of [
    'AudioStream',
    'sendVoiceTurn',
    'downloadVoiceAudio',
    'beginVoiceTurn',
    'interruptVoiceGeneration',
    'reportVoiceDelivery',
    'livekit',
  ]) {
    assert.equal(transport.includes(removed), false, `${removed} must not be used by V1`);
  }
  // Playback is a deliberate no-op: no automatic audio response in V1.
  assert.match(transport, /async playAnswer\(\): Promise<void> \{\s*return;\s*\}/);
});

test('the dictation service calls the STT-only endpoint, never /voice/turn', () => {
  assert.match(dictation, /\/api\/homi\/v1\/voice\/transcript/);
  assert.doesNotMatch(dictation, /buildHomiUrl\('\/api\/homi\/voice\/turn'\)/);
  assert.match(dictation, /semantic_turn: false/);
  assert.match(dictation, /tools_executed: false/);
  assert.match(dictation, /tts_generated: false/);
});

test('a transcript becomes an editable draft, not a sent message', () => {
  assert.match(surface, /setVoiceDraftReady\(true\)/);
  assert.match(surface, /voiceDraftPreviousTextRef\.current/);
  assert.match(surface, /setInput\(/);
  assert.match(surface, /handleDiscardVoiceDraft/);
  // No user/assistant message is created in the dictation handler.
  assert.equal(surface.includes('via_voice: true'), false);
  assert.equal(surface.includes('answer.spokenText'), false);
});

test('no T31 control path is reachable from the HOMI surface', () => {
  for (const removed of [
    'turnTakingReducer',
    'dispatchTurnTaking',
    'isGenerationCurrent',
    'beginTurn(',
    'playAnswer(',
    'reportDelivery(',
    'interruptGeneration(',
    "voice/turn'",
    'createRealtimeVoiceTransport',
    'createIosExpoGoTransport',
  ]) {
    assert.equal(surface.includes(removed), false, `${removed} must not be reachable`);
  }
  // The canonical text flow is still the one used on send.
  assert.match(surface, /deliverTurn\(\{ text, attachment: finalUploadedAttachment \}\)/);
});

test('the composer exposes the editable draft and a manual send', () => {
  assert.match(composer, /voiceDraft\?: boolean/);
  assert.match(composer, /onVoiceDraftDiscard/);
  assert.match(composer, /Borrador transcrito/);
  assert.match(composer, /Detener la grabación y transcribir/);
  assert.match(composer, /onSubmitEditing=\{handleSend\}/);
  assert.match(composer, /accessibilityLabel="Enviar el mensaje"/);
  // The old "Enviar lo que dijiste" button sent audio straight into THINK/TTS.
  assert.equal(composer.includes('Enviar lo que dijiste'), false);
});
