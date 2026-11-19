'use strict';
const { supabaseAdmin } = require('../config/supabase');
const { getHomeCloudContext } = require('./homecloud.context.service');
const { resolveHomeCloudCapabilities, assertHomeCloudCapability } = require('../lib/homecloudCapabilities');
const { createHttpError } = require('../lib/httpErrors');
const { mapAlbumRowToDto } = require('../lib/homecloudMappers');

const uuid = value => {
  if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value ?? '')) throw createHttpError(400, 'Identificador inválido.', 'homecloud_invalid_id');
  return value;
};
async function context(req) {
  const ctx = await getHomeCloudContext(req);
  assertHomeCloudCapability(resolveHomeCloudCapabilities({ role: ctx.membership.role, membershipStatus: ctx.membership.status, household: ctx.household }), 'homecloud.organize');
  if (!supabaseAdmin) throw createHttpError(503, 'Servicio no disponible.', 'backend_unavailable');
  return ctx;
}
const check = result => {
  if (result.error) throw createHttpError(500, 'No pudimos guardar los cambios del álbum.', 'homecloud_album_write_failed');
  return result.data;
};
async function album(ctx, id) {
  const value = check(await supabaseAdmin.from('homecloud_albums').select('*').eq('id', uuid(id)).eq('household_id', ctx.householdId).eq('lifecycle', 'active').maybeSingle());
  if (!value) throw createHttpError(404, 'Álbum no encontrado.', 'homecloud_album_not_found');
  return value;
}
function name(value) {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > 120) throw createHttpError(400, 'Ingresá un nombre de hasta 120 caracteres.', 'homecloud_invalid_album_name');
  return value.trim();
}
async function create(req) {
  const ctx = await context(req);
  const id = uuid(req.body?.id);
  const title = name(req.body?.name);
  // Client-generated intent ID makes retries safe without making names unique.
  const previous = check(await supabaseAdmin.from('homecloud_albums').select('*').eq('id', id).eq('household_id', ctx.householdId).maybeSingle());
  if (previous) {
    if (previous.name !== title || previous.lifecycle !== 'active') throw createHttpError(409, 'Esta solicitud ya fue utilizada.', 'homecloud_album_conflict');
    return mapAlbumRowToDto(previous);
  }
  const result = await supabaseAdmin.from('homecloud_albums').insert({ id, name: title, household_id: ctx.householdId, created_by_member_id: ctx.membership.id }).select('*').single();
  if (result.error?.code === '23505') {
    const existing = await album(ctx, id);
    if (existing.name !== title) throw createHttpError(409, 'Esta solicitud ya fue utilizada.', 'homecloud_album_conflict');
    return mapAlbumRowToDto(existing);
  }
  return mapAlbumRowToDto(check(result));
}
async function rename(req) {
  const ctx = await context(req);
  await album(ctx, req.params.albumId);
  return mapAlbumRowToDto(check(await supabaseAdmin.from('homecloud_albums').update({ name: name(req.body?.name) }).eq('id', req.params.albumId).eq('household_id', ctx.householdId).eq('lifecycle', 'active').select('*').single()));
}
async function trash(req) {
  const ctx = await context(req);
  await album(ctx, req.params.albumId);
  // Soft trash preserves every original and N:M membership for restoration.
  check(await supabaseAdmin.from('homecloud_albums').update({ lifecycle: 'trashed', trashed_at: new Date().toISOString(), trashed_by_member_id: ctx.membership.id }).eq('id', req.params.albumId).eq('household_id', ctx.householdId).eq('lifecycle', 'active'));
  return { trashed: true };
}
async function membership(req, remove = false) {
  const ctx = await context(req);
  await album(ctx, req.params.albumId);
  const contentId = uuid(req.params.contentId);
  const photo = check(await supabaseAdmin.from('homecloud_contents').select('id').eq('id', contentId).eq('household_id', ctx.householdId).eq('role', 'memory').eq('lifecycle', 'active').maybeSingle());
  if (!photo) throw createHttpError(404, 'Recuerdo no encontrado.', 'homecloud_content_not_found');
  check(remove
    ? await supabaseAdmin.from('homecloud_album_items').delete().eq('album_id', req.params.albumId).eq('content_id', contentId)
    : await supabaseAdmin.from('homecloud_album_items').upsert({ album_id: req.params.albumId, content_id: contentId, added_by_member_id: ctx.membership.id }, { onConflict: 'album_id,content_id', ignoreDuplicates: true }));
  return { albumId: req.params.albumId, contentId, included: !remove };
}
module.exports = { create, rename, trash, membership };
