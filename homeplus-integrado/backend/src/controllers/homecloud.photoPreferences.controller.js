'use strict';
const service = require('../services/homecloudPhotoPreferencesService');
const { sendApiError } = require('../lib/httpErrors');
const respond = fn => async (req, res) => {
  try { return res.status(200).json(await fn(req)); }
  catch (error) { return sendApiError(res, error, req); }
};
module.exports = { read: respond(service.read), favorite: respond(req => service.favorite(req, true)), unfavorite: respond(req => service.favorite(req, false)), cover: respond(service.cover) };
