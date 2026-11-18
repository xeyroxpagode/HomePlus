'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');

test('Planner Task rechaza origin_* público y usa sólo correlation.origin', () => {
  const controller = read('backend/src/controllers/planner.tasks.controller.js');
  const service = read('backend/src/services/planner.tasks.service.js');
  const createTask = service.slice(
    service.indexOf('const createTask = async'),
    service.indexOf('const getTaskCompletionAuthorization'),
  );

  assert.match(controller, /assertNoOriginInjection\(req\.body\)/);
  assert.match(controller, /protected_task_origin_field/);
  assert.match(service, /buildOriginPayload\(correlation\?\.origin\)/);
  assert.doesNotMatch(createTask, /body\?\.origin_/);
  assert.doesNotMatch(createTask, /body\.origin_/);
});

test('Assets e Inventory transportan origin por la correlación interna', () => {
  const assets = read('backend/src/services/assets.planner.service.js');
  const shopping = read('backend/src/inventory/shopping/shopping.service.js');

  assert.match(assets, /operation: 'assets\.planner_item\.create\.task',[\s\S]*?origin,/);
  assert.match(shopping, /operation:'inventory\.shopping_list\.planner_task',origin:/);
  assert.doesNotMatch(shopping, /requires_verification:false,origin_module:/);
});
