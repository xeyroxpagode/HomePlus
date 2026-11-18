'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const read = (relative) => fs.readFileSync(path.join(process.cwd(), relative), 'utf8');
const service = read('front/mi-front-limpio/services/homecloud/homecloudPhotoMemoryService.ts');
const component = read('front/mi-front-limpio/services/homecloud/PhotoMemoryIntake.tsx');
const screen = read('front/mi-front-limpio/screens/HomeCloudMemoriesScreen.tsx');
const backend = read('backend/src/services/homecloudIntakeService.js');

test('Memories creation is photo-only and avoids expensive picker payloads', () => {
  assert.match(service, /mediaTypes:\s*\['images'\]/);
  assert.match(service, /quality:\s*0\.82/);
  assert.match(service, /exif:\s*false/);
  assert.match(service, /base64:\s*false/);
  assert.doesNotMatch(service, /launchCameraAsync|startRecording|mediaTypes:\s*\[[^\]]*videos|role:\s*'written'/i);
});

test('photo upload reuses canonical private upload lifecycle and scoped recovery', () => {
  assert.match(service, /createUploadEngine/);
  assert.match(service, /createExpoFileSystemUploadTransport/);
  assert.match(service, /role:\s*'memory'/);
  assert.match(service, /initialAlbumId:\s*selectedAlbumId/);
  assert.match(service, /intakeSource/);
  assert.match(service, /recoverUploadJobs/);
});

test('Memories UI is one-tap gallery with optional album and inline retry', () => {
  assert.match(component, /Agregar foto/);
  assert.match(component, /Guardar en/);
  assert.match(component, /Reintentar/);
  assert.match(screen, /<PhotoMemoryIntake/);
  assert.doesNotMatch(screen, /<MemoryIntake/);
});

test('finalize response has a strict preview latency budget', () => {
  assert.match(backend, /PREVIEW_FINALIZE_BUDGET_MS\s*=\s*750/);
  assert.match(backend, /Promise\.race\(\[preview, budget\]\)/);
  assert.match(backend, /runPreviewAfterActiveWithinBudget\(finalized\)/);
});
