'use strict';
const { supabaseAdmin } = require('../config/supabase');
const { getHomeCloudContext } = require('./homecloud.context.service');
const { resolveHomeCloudCapabilities, assertHomeCloudCapability } = require('../lib/homecloudCapabilities');
const { createHttpError } = require('../lib/httpErrors');
const validId = id => /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id ?? '');
async function context(req, capability) {
  const ctx = await getHomeCloudContext(req);
  assertHomeCloudCapability(resolveHomeCloudCapabilities({ role: ctx.membership.role, membershipStatus: ctx.membership.status, household: ctx.household }), capability);
  if (!supabaseAdmin) throw createHttpError(503, 'Servicio no disponible.', 'backend_unavailable');
  return ctx;
}
function check(result) {
  if (result.error) throw createHttpError(503, 'Esta opción no está disponible por el momento.', 'homecloud_photo_preferences_unavailable');
  return result.data;
}
async function photo(ctx, id) {
  if (!validId(id)) throw createHttpError(400, 'Foto inválida.', 'homecloud_invalid_content_id');
  const row = check(await supabaseAdmin.from('homecloud_contents').select('id, mime_type').eq('id', id).eq('household_id', ctx.householdId).eq('role', 'memory').eq('lifecycle', 'active').maybeSingle());
  if (!row || !row.mime_type?.startsWith('image/')) throw createHttpError(404, 'Foto no encontrada.', 'homecloud_content_not_found');
}
async function read(req) {
  const ctx = await context(req, 'homecloud.view');
  const favorites = await supabaseAdmin.from('homecloud_memory_favorites').select('content_id, homecloud_contents!inner(household_id, lifecycle, role)').eq('account_id', ctx.accountId).eq('homecloud_contents.household_id', ctx.householdId).eq('homecloud_contents.lifecycle', 'active').eq('homecloud_contents.role', 'memory');
  const covers = await supabaseAdmin.from('homecloud_album_covers').select('album_id, content_id, homecloud_albums!inner(household_id, lifecycle), homecloud_contents!inner(household_id, lifecycle)').eq('homecloud_albums.household_id', ctx.householdId).eq('homecloud_albums.lifecycle', 'active').eq('homecloud_contents.household_id', ctx.householdId).eq('homecloud_contents.lifecycle', 'active');
  if ([favorites.error, covers.error].some(error => ['42P01', 'PGRST205'].includes(error?.code))) return { available: false };
  return { available: true, favoriteIds: check(favorites).map(row => row.content_id), covers: check(covers).map(row => ({ albumId: row.album_id, contentId: row.content_id })) };
}
async function favorite(req, enabled) {
  const ctx = await context(req, 'homecloud.view');
  await photo(ctx, req.params.contentId);
  check(enabled ? await supabaseAdmin.from('homecloud_memory_favorites').upsert({ account_id: ctx.accountId, content_id: req.params.contentId }, { onConflict: 'account_id,content_id', ignoreDuplicates: true }) : await supabaseAdmin.from('homecloud_memory_favorites').delete().eq('account_id', ctx.accountId).eq('content_id', req.params.contentId));
  return { favorite: enabled };
}
async function cover(req) {
  const ctx = await context(req, 'homecloud.organize');
  if (!validId(req.params.albumId)) throw createHttpError(400, 'Álbum inválido.', 'homecloud_invalid_id');
  await photo(ctx, req.params.contentId);
  const album = check(await supabaseAdmin.from('homecloud_albums').select('id').eq('id', req.params.albumId).eq('household_id', ctx.householdId).eq('lifecycle', 'active').maybeSingle());
  const member = check(await supabaseAdmin.from('homecloud_album_items').select('content_id').eq('album_id', req.params.albumId).eq('content_id', req.params.contentId).maybeSingle());
  if (!album || !member) throw createHttpError(404, 'La foto debe pertenecer al álbum.', 'homecloud_album_not_found');
  check(await supabaseAdmin.from('homecloud_album_covers').upsert({ album_id: req.params.albumId, content_id: req.params.contentId }, { onConflict: 'album_id' }));
  return { albumId: req.params.albumId, contentId: req.params.contentId };
}
module.exports = { read, favorite, cover };
