const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const { after, test } = require('node:test');
const ts = require('typescript');

const previousTsExtension = Module._extensions['.ts'];
Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
    fileName: filename,
  });
  module._compile(output.outputText, filename);
};

class FakeFormData {
  constructor() {
    this.parts = [];
  }

  append(name, value) {
    this.parts.push([name, value]);
  }
}

class FakeXMLHttpRequest {
  static instances = [];

  constructor() {
    this.headers = {};
    this.status = 0;
    this.responseText = '';
    this.onload = null;
    this.onerror = null;
    this.ontimeout = null;
    this.onabort = null;
    this.sentBody = null;
    this.aborted = false;
    FakeXMLHttpRequest.instances.push(this);
  }

  open(method, url) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name, value) {
    this.headers[name] = value;
  }

  send(body) {
    this.sentBody = body;
    queueMicrotask(() => {
      this.status = 201;
      this.responseText = '{"ok":true}';
      this.onload?.();
    });
  }

  abort() {
    this.aborted = true;
    this.onabort?.();
  }
}

const originalFormData = global.FormData;
const originalXMLHttpRequest = global.XMLHttpRequest;

global.FormData = FakeFormData;
global.XMLHttpRequest = FakeXMLHttpRequest;

const {
    isHomiProposalAction,
  } = require(path.join(__dirname, '..', 'services', 'homi', 'homiContract.ts'));
  const {
    buildMultipartHeaders,
    MultipartTransportError,
    postMultipartText,
  } = require(path.join(__dirname, '..', 'services', 'homi', 'homiMultipart.ts'));

  test('proposal action accepts only confirm and cancel', () => {
    assert.equal(isHomiProposalAction('confirm'), true);
    assert.equal(isHomiProposalAction('cancel'), true);
    assert.equal(isHomiProposalAction('approve'), false);
    assert.equal(isHomiProposalAction('CONFIRM'), false);
    assert.equal(isHomiProposalAction(undefined), false);
  });

  test('multipart transport removes Content-Type and preserves Authorization', () => {
    assert.deepEqual(
      buildMultipartHeaders({
        Authorization: 'Bearer test-token',
        'Content-Type': 'multipart/form-data',
        'X-Household-Id': 'household-test',
      }),
      {
        Authorization: 'Bearer test-token',
        'X-Household-Id': 'household-test',
      },
    );
  });

  test('multipart transport sends the React Native file part unchanged', async () => {
    const formData = new FormData();
    formData.append('file', {
      uri: 'file:///tmp/reporte ñ.pdf',
      name: 'reporte ñ.pdf',
      type: 'application/pdf',
    });

    const response = await postMultipartText({
      url: 'http://127.0.0.1:3002/api/homi/v1/attachments/upload',
      body: formData,
      headers: {
        Authorization: 'Bearer test-token',
      },
      timeoutMs: 60000,
    });

    assert.equal(response.status, 201);
    assert.equal(response.ok, true);
    assert.equal(response.text, '{"ok":true}');

    const xhr = FakeXMLHttpRequest.instances.at(-1);
    assert.equal(xhr.method, 'POST');
    assert.equal(xhr.sentBody, formData);
    assert.deepEqual(formData.parts[0], [
      'file',
      {
        uri: 'file:///tmp/reporte ñ.pdf',
        name: 'reporte ñ.pdf',
        type: 'application/pdf',
      },
    ]);
    assert.equal(xhr.headers.Authorization, 'Bearer test-token');
    assert.equal(
      Object.keys(xhr.headers).some(
        (name) => name.toLowerCase() === 'content-type',
      ),
      false,
    );
  });

  test('multipart transport maps an external abort to an aborted failure', async () => {
    const controller = new AbortController();
    const promise = postMultipartText({
      url: 'http://127.0.0.1:3002/api/homi/v1/attachments/upload',
      body: new FormData(),
      headers: {},
      signal: controller.signal,
      timeoutMs: 60000,
    });

    controller.abort();

    await assert.rejects(
      promise,
      (error) =>
        error instanceof MultipartTransportError && error.code === 'aborted',
    );
  });

after(() => {
  global.FormData = originalFormData;
  global.XMLHttpRequest = originalXMLHttpRequest;
  Module._extensions['.ts'] = previousTsExtension;
});
