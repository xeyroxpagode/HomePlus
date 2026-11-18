const { supabaseAdmin } = require('../config/supabase')
const { createHttpError } = require('../lib/httpErrors')

const BUCKET = 'messaging-attachments'
const MAX_BYTES = 50 * 1024 * 1024
const MIME_BY_KIND = {
  image: new Set(['image/jpeg', 'image/png', 'image/webp']),
  audio: new Set(['audio/m4a', 'audio/mp4', 'audio/mpeg', 'audio/ogg', 'audio/wav']),
  file: new Set(['application/pdf', 'text/plain', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']),
}

const requireAdmin = () => {
  if (!supabaseAdmin) throw createHttpError(503, 'El almacenamiento de Mensajes no está configurado.', 'messaging_storage_unavailable')
  return supabaseAdmin
}

const normalize = (value) => typeof value === 'string' ? value.trim() : ''
const assertUuid = (value, code = 'messaging_invalid_attachment') => {
  if (typeof value !== 'string' || !/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(value)) throw createHttpError(400, 'El adjunto no es válido.', code)
}
const validateInput = (payload = {}) => {
  const kind = normalize(payload.kind)
  const mimeType = normalize(payload.mime_type).toLowerCase()
  const originalName = normalize(payload.original_name).replace(/[\\/\0]/g, '_')
  const size = Number(payload.size_bytes)
  assertUuid(payload.client_attachment_id)
  if (!MIME_BY_KIND[kind]?.has(mimeType)) throw createHttpError(400, 'El tipo de archivo no está permitido.', 'messaging_attachment_invalid_mime')
  if (!originalName || originalName.length > 180) throw createHttpError(400, 'El nombre del archivo no es válido.', 'messaging_attachment_invalid_name')
  if (!Number.isInteger(size) || size < 1 || size > MAX_BYTES) throw createHttpError(400, 'El archivo supera el límite permitido de 50 MB.', 'messaging_attachment_invalid_size')
  const optionalNumber = (value, field) => value == null ? null : (Number.isInteger(Number(value)) && Number(value) >= 0 ? Number(value) : (() => { throw createHttpError(400, `Metadato ${field} inválido.`, 'messaging_attachment_invalid_metadata') })())
  return { kind, mimeType, originalName, sizeBytes: size, clientAttachmentId: payload.client_attachment_id, width: optionalNumber(payload.width, 'width'), height: optionalNumber(payload.height, 'height'), durationMs: optionalNumber(payload.duration_ms, 'duration_ms') }
}

const getConversation = async (context, conversationId) => {
  const { data, error } = await context.client.from('messaging_conversations').select('id, household_id').eq('id', conversationId).eq('household_id', context.householdId).is('archived_at', null).maybeSingle()
  if (error) throw createHttpError(500, 'No pudimos consultar la conversación.', 'messaging_attachment_conversation_lookup_failed')
  if (!data) throw createHttpError(404, 'No encontraste esta conversación.', 'messaging_not_found')
  return data
}

const mapAttachment = (row) => ({
  id: row.id, message_id: row.message_id, household_id: row.household_id, conversation_id: row.conversation_id,
  kind: row.attachment_kind, mime_type: row.mime_type, original_name: row.original_name, size_bytes: Number(row.size_bytes),
  width: row.width, height: row.height, duration_ms: row.duration_ms, lifecycle: row.lifecycle, created_at: row.created_at,
})

const register = async (context, conversationId, payload) => {
  const input = validateInput(payload)
  await getConversation(context, conversationId)
  const admin = requireAdmin()
  const { data: existing, error: existingError } = await admin.from('messaging_attachments').select('*')
    .eq('conversation_id', conversationId).eq('created_by_membership_id', context.membershipId).eq('client_attachment_id', input.clientAttachmentId).maybeSingle()
  if (existingError) throw createHttpError(500, 'No pudimos preparar el adjunto.', 'messaging_attachment_lookup_failed')
  if (existing) return { attachment: mapAttachment(existing) }
  const id = require('crypto').randomUUID()
  const storagePath = `${context.householdId}/messages/${conversationId}/${id}`
  const { data, error } = await admin.from('messaging_attachments').insert({
    id, household_id: context.householdId, conversation_id: conversationId, created_by_membership_id: context.membershipId,
    client_attachment_id: input.clientAttachmentId, attachment_kind: input.kind, mime_type: input.mimeType, original_name: input.originalName,
    size_bytes: input.sizeBytes, width: input.width || null, height: input.height || null, duration_ms: input.durationMs, storage_bucket: BUCKET, storage_path: storagePath,
  }).select('*').single()
  if (error) throw createHttpError(500, 'No pudimos preparar el adjunto.', 'messaging_attachment_register_failed')
  return { attachment: mapAttachment(data) }
}

const ownedAttachment = async (context, attachmentId) => {
  assertUuid(attachmentId)
  const admin = requireAdmin()
  const { data, error } = await admin.from('messaging_attachments').select('*').eq('id', attachmentId).eq('household_id', context.householdId).eq('created_by_membership_id', context.membershipId).maybeSingle()
  if (error) throw createHttpError(500, 'No pudimos consultar el adjunto.', 'messaging_attachment_lookup_failed')
  if (!data) throw createHttpError(404, 'Adjunto no encontrado.', 'messaging_attachment_not_found')
  await getConversation(context, data.conversation_id)
  return data
}

const authorizeUpload = async (context, attachmentId) => {
  const attachment = await ownedAttachment(context, attachmentId)
  if (!['uploading', 'failed'].includes(attachment.lifecycle) || attachment.message_id) throw createHttpError(409, 'Este adjunto ya no puede cargarse.', 'messaging_attachment_not_uploadable')
  const { data, error } = await requireAdmin().storage.from(BUCKET).createSignedUploadUrl(attachment.storage_path)
  if (error || !data?.signedUrl) throw createHttpError(500, 'No pudimos autorizar la carga.', 'messaging_attachment_upload_authorization_failed')
  return { attachment: mapAttachment(attachment), signed_upload_url: data.signedUrl, bucket: BUCKET, path: attachment.storage_path }
}

const verifyUpload = async (context, attachmentId) => {
  const attachment = await ownedAttachment(context, attachmentId)
  if (attachment.lifecycle === 'uploaded' || attachment.lifecycle === 'committed') return { attachment: mapAttachment(attachment), verified: true }
  const parent = attachment.storage_path.slice(0, attachment.storage_path.lastIndexOf('/'))
  const name = attachment.storage_path.slice(attachment.storage_path.lastIndexOf('/') + 1)
  const { data: listed, error } = await requireAdmin().storage.from(BUCKET).list(parent, { limit: 10 })
  if (error) throw createHttpError(500, 'No pudimos verificar la carga.', 'messaging_attachment_verify_failed')
  const object = (listed ?? []).find((entry) => entry.name === name)
  if (!object) throw createHttpError(409, 'La carga todavía no está disponible.', 'messaging_attachment_missing_upload')
  const actualSize = Number(object.metadata?.size ?? 0)
  if (actualSize && actualSize !== Number(attachment.size_bytes)) throw createHttpError(400, 'El tamaño del archivo no coincide.', 'messaging_attachment_size_mismatch')
  const { data, error: updateError } = await requireAdmin().from('messaging_attachments').update({ lifecycle: 'uploaded', uploaded_at: new Date().toISOString() }).eq('id', attachment.id).in('lifecycle', ['uploading', 'failed']).select('*').single()
  if (updateError) throw createHttpError(500, 'No pudimos finalizar la carga.', 'messaging_attachment_verify_update_failed')
  return { attachment: mapAttachment(data ?? attachment), verified: true }
}

const cancelUpload = async (context, attachmentId) => {
  const attachment = await ownedAttachment(context, attachmentId)
  if (attachment.lifecycle === 'committed' || attachment.message_id) return { cancelled: false, committed: true }
  // This is the orphan recovery path: it is deliberately scoped to the
  // creator's uncommitted canonical object, never a broad Storage delete.
  await requireAdmin().storage.from(BUCKET).remove([attachment.storage_path]).catch(() => {})
  const { error } = await requireAdmin().from('messaging_attachments').update({ lifecycle: 'failed' }).eq('id', attachment.id).is('message_id', null)
  if (error) throw createHttpError(500, 'No pudimos cancelar la carga.', 'messaging_attachment_cancel_failed')
  return { cancelled: true, committed: false }
}

const getDownload = async (context, attachmentId) => {
  assertUuid(attachmentId)
  const { data: attachment, error } = await context.client.from('messaging_attachments').select('*').eq('id', attachmentId).eq('household_id', context.householdId).maybeSingle()
  if (error) throw createHttpError(500, 'No pudimos consultar el adjunto.', 'messaging_attachment_lookup_failed')
  if (!attachment || attachment.lifecycle !== 'committed' || !attachment.message_id) throw createHttpError(404, 'Adjunto no disponible.', 'messaging_attachment_not_available')
  const { data, error: signedError } = await requireAdmin().storage.from(BUCKET).createSignedUrl(attachment.storage_path, 300)
  if (signedError || !data?.signedUrl) throw createHttpError(500, 'No pudimos abrir el adjunto.', 'messaging_attachment_download_failed')
  return { attachment: mapAttachment(attachment), signed_url: data.signedUrl, expires_in: 300 }
}

const linkTaskAction = async (context, messageId, payload = {}) => {
  assertUuid(messageId, 'messaging_invalid_message')
  assertUuid(payload.task_id, 'messaging_invalid_task_reference')
  const { data: message, error: messageError } = await context.client.from('messaging_messages')
    .select('id, conversation_id').eq('id', messageId).maybeSingle()
  if (messageError) throw createHttpError(500, 'No pudimos consultar el mensaje.', 'messaging_action_message_lookup_failed')
  if (!message) throw createHttpError(404, 'Mensaje no encontrado.', 'messaging_not_found')
  const admin = requireAdmin()
  const { data: task, error: taskError } = await admin.from('planner_tasks').select('id, household_id, trashed_at').eq('id', payload.task_id).maybeSingle()
  if (taskError) throw createHttpError(500, 'No pudimos consultar la tarea.', 'messaging_action_task_lookup_failed')
  if (!task || task.household_id !== context.householdId || task.trashed_at) throw createHttpError(404, 'Tarea no disponible.', 'messaging_action_task_not_found')
  const { data: existing, error: existingError } = await admin.from('messaging_message_actions').select('id, message_id, action_type, entity_id, created_at').eq('message_id', message.id).eq('action_type', 'task').maybeSingle()
  if (existingError) throw createHttpError(500, 'No pudimos consultar la acción.', 'messaging_action_lookup_failed')
  if (existing) return { action: existing }
  const { data, error } = await admin.from('messaging_message_actions').insert({
    message_id: message.id, household_id: context.householdId, conversation_id: message.conversation_id,
    created_by_membership_id: context.membershipId, action_type: 'task', entity_id: task.id,
  }).select('id, message_id, action_type, entity_id, created_at').single()
  if (error) {
    const { data: raced } = await admin.from('messaging_message_actions').select('id, message_id, action_type, entity_id, created_at').eq('message_id', message.id).eq('action_type', 'task').maybeSingle()
    if (raced) return { action: raced }
    throw createHttpError(500, 'No pudimos vincular la tarea.', 'messaging_action_link_failed')
  }
  return { action: data }
}

module.exports = { register, authorizeUpload, verifyUpload, cancelUpload, getDownload, linkTaskAction, mapAttachment, MIME_BY_KIND, MAX_BYTES }
