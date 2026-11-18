const { getPlannerContext } = require('../services/planner.context.service')
const messaging = require('../services/messaging.service')
const attachments = require('../services/messagingAttachments.service')

const listConversations = async (req, res, next) => {
  try { res.json(await messaging.listConversations(await getPlannerContext(req))) } catch (error) { next(error) }
}

const getConversation = async (req, res, next) => {
  try { res.json(await messaging.getConversation(await getPlannerContext(req), req.params.conversationId)) } catch (error) { next(error) }
}

const ensureDirectConversation = async (req, res, next) => {
  try { res.status(200).json(await messaging.ensureDirectConversation(await getPlannerContext(req), req.body?.other_membership_id)) } catch (error) { next(error) }
}

const listMessages = async (req, res, next) => {
  try { res.json(await messaging.listMessages(await getPlannerContext(req), req.params.conversationId, req.query)) } catch (error) { next(error) }
}

const sendMessage = async (req, res, next) => {
  try { res.status(201).json(await messaging.sendMessage(await getPlannerContext(req), req.params.conversationId, req.body)) } catch (error) { next(error) }
}

const markConversationRead = async (req, res, next) => {
  try { res.json(await messaging.markConversationRead(await getPlannerContext(req), req.params.conversationId, req.body)) } catch (error) { next(error) }
}
const toggleReaction = async (req, res, next) => {
  try { res.json(await messaging.toggleReaction(await getPlannerContext(req), req.params.messageId, req.body)) } catch (error) { next(error) }
}
const registerAttachment = async (req, res, next) => {
  try { res.status(201).json(await attachments.register(await getPlannerContext(req), req.params.conversationId, req.body)) } catch (error) { next(error) }
}
const authorizeAttachmentUpload = async (req, res, next) => {
  try { res.json(await attachments.authorizeUpload(await getPlannerContext(req), req.params.attachmentId)) } catch (error) { next(error) }
}
const verifyAttachmentUpload = async (req, res, next) => {
  try { res.json(await attachments.verifyUpload(await getPlannerContext(req), req.params.attachmentId)) } catch (error) { next(error) }
}
const cancelAttachmentUpload = async (req, res, next) => {
  try { res.json(await attachments.cancelUpload(await getPlannerContext(req), req.params.attachmentId)) } catch (error) { next(error) }
}
const getAttachmentDownload = async (req, res, next) => {
  try { res.json(await attachments.getDownload(await getPlannerContext(req), req.params.attachmentId)) } catch (error) { next(error) }
}
const linkTaskAction = async (req, res, next) => {
  try { res.status(201).json(await attachments.linkTaskAction(await getPlannerContext(req), req.params.messageId, req.body)) } catch (error) { next(error) }
}

module.exports = { listConversations, getConversation, ensureDirectConversation, listMessages, sendMessage, markConversationRead, toggleReaction, registerAttachment, authorizeAttachmentUpload, verifyAttachmentUpload, cancelAttachmentUpload, getAttachmentDownload, linkTaskAction }
