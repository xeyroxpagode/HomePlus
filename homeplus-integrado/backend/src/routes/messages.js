const express = require('express')
const authFinalMiddleware = require('../middleware/authFinalMiddleware')
const controller = require('../controllers/messaging.controller')

const router = express.Router()
router.use(authFinalMiddleware)

router.get('/conversations', controller.listConversations)
router.post('/directs/ensure', controller.ensureDirectConversation)
router.get('/conversations/:conversationId', controller.getConversation)
router.get('/conversations/:conversationId/messages', controller.listMessages)
router.post('/conversations/:conversationId/messages', controller.sendMessage)
router.post('/conversations/:conversationId/attachments', controller.registerAttachment)
router.post('/conversations/:conversationId/read', controller.markConversationRead)
router.post('/:messageId/reaction', controller.toggleReaction)
router.post('/:messageId/actions/task', controller.linkTaskAction)
router.post('/attachments/:attachmentId/upload', controller.authorizeAttachmentUpload)
router.post('/attachments/:attachmentId/verify', controller.verifyAttachmentUpload)
router.post('/attachments/:attachmentId/cancel', controller.cancelAttachmentUpload)
router.get('/attachments/:attachmentId/download', controller.getAttachmentDownload)

module.exports = router
