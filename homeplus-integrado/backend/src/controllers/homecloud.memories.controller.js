'use strict';
const { trashPhotoMemory } = require('../services/homecloudMemoriesService');
const { sendApiError } = require('../lib/httpErrors');
async function trash(req, res) {
  try { res.json(await trashPhotoMemory(req)); } catch (error) { return sendApiError(res, error, req); }
}
module.exports = { trash };
