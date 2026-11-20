'use strict';

const express = require('express');
const router = express.Router();
const authFinalMiddleware = require('../middleware/authFinalMiddleware');
const controller = require('../controllers/homiV1.controller');

router.get('/health', controller.health);

router.use(authFinalMiddleware);

router.get('/tools', controller.listTools);
router.post('/tools/:toolId/invoke', controller.invokeTool);
router.post('/text/turn', controller.textTurn);
router.post(
  '/voice/transcript',
  express.raw({ type: () => true, limit: '12mb' }),
  controller.voiceTranscript
);
router.post('/internal/tools/:toolId/execute', controller.internalExecute);

module.exports = router;
