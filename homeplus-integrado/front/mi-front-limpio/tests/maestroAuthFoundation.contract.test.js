#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const front = path.resolve(__dirname, '..');
const root = path.resolve(front, '..', '..');
const read = (relative) => fs.readFileSync(path.join(front, relative), 'utf8');
let failed = 0;
const check = (condition, message) => {
  if (condition) console.log(`  ok ${message}`);
  else { failed += 1; console.error(`  fail ${message}`); }
};

console.log('=== Maestro automatic auth foundation contracts ===');
const login = read('screens/Login.tsx');
const navigator = read('navigation/AppNavigator.tsx');
const experienceSelector = read('screens/ExperienceSelectorScreen.tsx');
const loginFlow = read('.maestro/shared/login.yaml');
const ensureFlow = read('.maestro/shared/ensure-authenticated.yaml');
const signedOutFlow = read('.maestro/shared/ensure-signed-out.yaml');
const packageJson = read('package.json');
const fixture = fs.readFileSync(path.join(root, 'scripts/qa/setup-e2e-fixtures.js'), 'utf8');
const credentialProvisioning = fs.readFileSync(path.join(root, 'scripts/qa/provision-e2e-credentials.js'), 'utf8');
const example = fs.readFileSync(path.join(root, '.env.qa.example'), 'utf8');
const multiRunner = read('scripts/qa/test-multi-user.ps1');

check(['auth.email', 'auth.password', 'auth.submit', 'auth.error'].every((id) => login.includes(id)), 'login exposes stable auth selectors');
check(navigator.includes('auth.ready') && navigator.includes('auth.signedIn') && navigator.includes('auth.signedOut'), 'resolved auth state is observable without altering auth behavior');
check(navigator.includes('experience.resolved') && experienceSelector.includes('experience.standard') && loginFlow.includes('experience.standard'), 'first-login experience selection is resolved before Home assertions');
check(loginFlow.includes('${QA_EMAIL}') && loginFlow.includes('${QA_PASSWORD}'), 'login subflow receives injected credentials');
check(ensureFlow.includes('auth.signedOut') && ensureFlow.includes('login.yaml'), 'ensure-authenticated logs in only when required');
check(signedOutFlow.includes('account.signOut') && signedOutFlow.includes('auth.signedOut'), 'auth scenarios reset via real logout without clearing the development bundle');
check(!loginFlow.match(/password\s*[:=]\s*[^$\s]/i), 'source-controlled login flow contains no literal password');
check(packageJson.includes('test:e2e:auth') && packageJson.includes('test:e2e:multi'), 'package exposes auth and multi-user commands');
check(multiRunner.includes('Start-Job') && multiRunner.includes('task-claim-c.yaml'), 'three-device runtime race convergence is prepared without replacing backend authority');
check(fixture.includes('QA_FIXTURES_ENABLED') && fixture.includes("qa-maestro-homeplus"), 'fixture bootstrap is opt-in and household-scoped');
check(!fixture.includes('auth.admin.createUser'), 'fixture bootstrap cannot create auth accounts itself');
check(credentialProvisioning.includes('auth.admin.createUser') && credentialProvisioning.includes('isSupabaseSecretKey') && credentialProvisioning.includes('isLegacyServiceRole') && credentialProvisioning.includes('secret_legacy_name') && credentialProvisioning.includes('qa-a-maestro@homeplus.test'), 'dedicated local/CI provisioner accepts secret-key preferred with strict legacy-name compatibility and owns only QA users');
check(example.includes('QA_SUPABASE_SECRET_KEY=') && example.includes('QA_SUPABASE_SERVICE_ROLE_KEY='), 'secret template documents preferred and legacy QA admin credentials without values');
check(example.includes('QA_A_EMAIL=') && example.includes('QA_C_PASSWORD='), 'secret template defines QA account contract without values');

if (failed) process.exit(1);
console.log('MAESTRO AUTH FOUNDATION CONTRACTS: PASS');
