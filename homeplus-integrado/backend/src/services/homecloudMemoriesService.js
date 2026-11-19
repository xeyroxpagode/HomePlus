'use strict';
const { supabaseAdmin } = require('../config/supabase');
const { getHomeCloudContext } = require('./homecloud.context.service');
const { resolveHomeCloudCapabilities, assertHomeCloudCapability } = require('../lib/homecloudCapabilities');
const { createHttpError } = require('../lib/httpErrors');

// Existing trashed lifecycle: no binary deletion, no new schema or permissions.
async function trashPhotoMemory(req) {
  const context = await getHomeCloudContext(req);
  const capabilities = resolveHomeCloudCapabilities({ role: context.membership.role, membershipStatus: context.membership.status, household: context.household });
  assertHomeCloudCapability(capabilities, 'homecloud.delete');
  const id = req.params.contentId;
  if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id ?? '')) throw createHttpError(400, 'Recuerdo inválido.', 'homecloud_invalid_content_id');
  if (!supabaseAdmin) throw createHttpError(503, 'Servicio no disponible.', 'storage_backend_unavailable');
  const { data, error } = await supabaseAdmin.from('homecloud_contents').select('id, lifecycle').eq('id', id).eq('household_id', context.householdId).eq('role', 'memory').maybeSingle();
  if (error) throw createHttpError(500, 'No pudimos consultar el recuerdo.', 'homecloud_memory_lookup_failed');
  if (!data) throw createHttpError(404, 'Recuerdo no encontrado.', 'homecloud_content_not_found');
  if (data.lifecycle === 'trashed') return { contentId: id, trashed: true };
  if (data.lifecycle !== 'active') throw createHttpError(409, 'La foto todavía no está lista.', 'homecloud_memory_not_ready');
  const result = await supabaseAdmin.from('homecloud_contents').update({ lifecycle: 'trashed', trashed_at: new Date().toISOString(), trashed_by_member_id: context.membership.id }).eq('id', id).eq('household_id', context.householdId).eq('role', 'memory').eq('lifecycle', 'active');
  if (result.error) throw createHttpError(500, 'No pudimos eliminar el recuerdo.', 'homecloud_memory_trash_failed');
  return { contentId: id, trashed: true };
}
module.exports = { trashPhotoMemory };
