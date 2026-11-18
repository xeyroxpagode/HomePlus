const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('../front/mi-front-limpio/node_modules/typescript');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'front/mi-front-limpio/services/authMeContract.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exportsUnderTest = {};
vm.runInNewContext(compiled, { exports: exportsUnderTest });
const { parseAuthMeProjection } = exportsUnderTest;

test('valid account projection preserves the original response', () => {
  const account = { memberships: [], navigation: { next: 'home' }, person: null, active_household: null };
  assert.equal(parseAuthMeProjection(account), account);
});

test('missing or malformed projections fail before navigation access', () => {
  for (const payload of [undefined, null, [], {}, { memberships: [] },
    { memberships: [], navigation: { next: null } },
    { memberships: [], navigation: { next: 'home' }, person: null }]) {
    assert.throws(() => parseAuthMeProjection(payload), { name: 'TypeError' });
  }
});

test('auth projection is validated before navigation is consumed', () => {
  const api = fs.readFileSync(path.join(root, 'front/mi-front-limpio/services/api.ts'), 'utf8');
  const contract = fs.readFileSync(path.join(root, 'front/mi-front-limpio/services/authMeContract.ts'), 'utf8');

  assert.match(api, /await requestJson<unknown>\('\/api\/auth\/me'/);
  assert.match(api, /parseAuthMeProjection\(payload\)/);
  assert.match(api, /auth_me_invalid_contract/);
  assert.match(contract, /typeof value\.navigation\.next !== 'string'/);
  assert.match(contract, /Array\.isArray\(value\.memberships\)/);
});
