const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require(path.join(__dirname, '..', 'front', 'mi-front-limpio', 'node_modules', 'typescript'));

const previousTsExtension = Module._extensions['.ts'];
Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  });
  module._compile(output.outputText, filename);
};

async function main() {
  try {
    const failure = require('../front/mi-front-limpio/services/core/requestFailure.ts');
    const { createRequestControl } = require('../front/mi-front-limpio/services/core/requestControl.ts');
    const contextSource = fs.readFileSync(path.join(__dirname, '..', 'front', 'mi-front-limpio', 'context', 'FeatureFlagsContext.tsx'), 'utf8');

    assert.equal(
      failure.classifyTransportFailure(new Error('Fetch request has been canceled'), { signalAborted: false, abortReason: 'unknown' }),
      'cancelled',
      'iOS native cancellation is classified as request.cancelled, never network-error',
    );
    assert.equal(
      failure.classifyTransportFailure(new Error('anything'), { signalAborted: true, abortReason: 'timeout' }),
      'timeout',
      'timeout keeps its own classification',
    );
    assert.equal(
      failure.classifyTransportFailure(new Error('Network request failed'), { signalAborted: false, abortReason: 'unknown' }),
      'offline',
      'real connectivity failure is not hidden as cancellation',
    );

    const external = new AbortController();
    const control = createRequestControl({ signal: external.signal });
    external.abort();
    assert.equal(control.signal.aborted, true, 'external lifecycle cancellation reaches the transport');
    assert.equal(control.getAbortReason(), 'external', 'external cancellation keeps its reason');
    control.dispose();

    const replacement = new AbortController();
    const replacementControl = createRequestControl({ signal: replacement.signal });
    replacement.abort('feature_flags.replaced');
    assert.equal(replacementControl.getAbortReason(), 'feature_flags.replaced', 'feature-flag replacement records its explicit lifecycle reason');
    replacementControl.dispose();

    const timeout = createRequestControl({ timeoutMs: 5 });
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(timeout.getAbortReason(), 'timeout', 'timeout does not become an unclassified cancellation');
    timeout.dispose();

    assert.match(contextSource, /inflightRequest\.current\?\.key === requestKey/, 'same feature-flag scope reuses its in-flight request');
    assert.match(contextSource, /setStatus\('cancelled'\)/, 'cancelled feature-flag requests always settle loading state');
    assert.match(contextSource, /setStatus\('fallback'\)/, 'real feature-flag errors keep a deny-safe fallback state');
    assert.match(contextSource, /component\.unmount/, 'provider unmount is development-instrumented');

    console.log('Feature-flag request lifecycle: PASS');
  } finally {
    Module._extensions['.ts'] = previousTsExtension;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
