'use strict';
const albums = require('../services/homecloudAlbumsService');
const { sendApiError } = require('../lib/httpErrors');
const respond = (fn, key) => async (req, res) => {
  try { return res.status(200).json({ [key]: await fn(req) }); }
  catch (error) { return sendApiError(res, error, req); }
};
module.exports = {
  create: respond(albums.create, 'album'),
  rename: respond(albums.rename, 'album'),
  trash: respond(albums.trash, 'result'),
  add: respond(req => albums.membership(req), 'membership'),
  remove: respond(req => albums.membership(req, true), 'membership'),
};
