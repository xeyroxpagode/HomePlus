const { createHttpError } = require('../lib/httpErrors')
const { mapAttachment } = require('./messagingAttachments.service')

const DEFAULT_PAGE_SIZE = 40
const MAX_PAGE_SIZE = 80

const parsePageSize = (value) => {
  const parsed = Number.parseInt(String(value ?? DEFAULT_PAGE_SIZE), 10)
  if (!Number.isFinite(parsed)) return DEFAULT_PAGE_SIZE
  return Math.min(Math.max(parsed, 1), MAX_PAGE_SIZE)
}

const rpcError = (error, fallbackCode = 'messaging_operation_failed') => {
  const code = error?.code
  if (code === '42501') return createHttpError(403, 'No tenés acceso a esta conversación.', 'messaging_forbidden')
  if (code === 'P0002') return createHttpError(404, 'No encontramos esta conversación.', 'messaging_not_found')
  if (code === '22023') return createHttpError(400, 'Los datos del mensaje no son válidos.', 'messaging_invalid_request')
  return createHttpError(500, error?.message ?? 'No pudimos completar Mensajes.', fallbackCode)
}

const mapMember = (row) => row ? {
  membership_id: row.membership_id,
  person_id: row.person_id,
  display_name: row.display_name,
  avatar_url: row.avatar_url ?? null,
  role: row.role,
} : null

const mapMessage = (row, membersById, reactionsByMessageId = new Map(), attachmentsByMessageId = new Map()) => ({
  id: row.id,
  conversation_id: row.conversation_id,
  sender_membership_id: row.sender_membership_id,
  sender: mapMember(membersById.get(row.sender_membership_id)),
  type: row.message_type,
  body: row.body,
  context_entity_id: row.context_entity_id ?? null,
  client_message_id: row.client_message_id,
  sequence: Number(row.sequence),
  created_at: row.created_at,
  edited_at: row.edited_at,
  deleted_at: row.deleted_at,
  reactions: reactionsByMessageId.get(row.id) ?? [],
  attachments: attachmentsByMessageId.get(row.id) ?? [],
})

const loadAttachments = async (client, messageIds) => {
  if (!messageIds.length) return new Map()
  const { data, error } = await client.from('messaging_attachments').select('*').in('message_id', messageIds).eq('lifecycle', 'committed')
  if (error) throw rpcError(error, 'messaging_attachments_lookup_failed')
  const grouped = new Map()
  ;(data ?? []).forEach((attachment) => {
    const values = grouped.get(attachment.message_id) ?? []
    values.push(mapAttachment(attachment))
    grouped.set(attachment.message_id, values)
  })
  return grouped
}

const loadReactions = async (client, messageIds, membershipId) => {
  if (!messageIds.length) return new Map()
  const { data, error } = await client
    .from('messaging_message_reactions')
    .select('message_id, membership_id, reaction_type')
    .in('message_id', messageIds)
  if (error) throw rpcError(error, 'messaging_reactions_lookup_failed')
  const grouped = new Map()
  ;(data ?? []).forEach((reaction) => {
    const current = grouped.get(reaction.message_id) ?? []
    const index = current.findIndex((item) => item.reaction_type === reaction.reaction_type)
    if (index >= 0) {
      current[index] = { ...current[index], count: current[index].count + 1, mine: current[index].mine || reaction.membership_id === membershipId }
    } else current.push({ reaction_type: reaction.reaction_type, count: 1, mine: reaction.membership_id === membershipId })
    grouped.set(reaction.message_id, current)
  })
  return grouped
}

const loadPublicMembers = async (client, membershipIds) => {
  const ids = [...new Set(membershipIds.filter(Boolean))]
  if (!ids.length) return new Map()
  const { data, error } = await client
    .from('household_people_public')
    .select('membership_id, person_id, display_name, avatar_url, role')
    .in('membership_id', ids)
  if (error) throw rpcError(error, 'messaging_members_lookup_failed')
  return new Map((data ?? []).map((member) => [member.membership_id, member]))
}

const ensureHouseholdConversation = async (context) => {
  const { data, error } = await context.client.rpc('messaging_ensure_household_conversation', {
    p_household_id: context.householdId,
  })
  if (error) throw rpcError(error, 'messaging_household_ensure_failed')
  return data
}

const getConversationOrThrow = async (context, conversationId) => {
  const { data, error } = await context.client
    .from('messaging_conversations')
    .select('*')
    .eq('id', conversationId)
    .eq('household_id', context.householdId)
    .is('archived_at', null)
    .maybeSingle()
  if (error) throw rpcError(error, 'messaging_conversation_lookup_failed')
  if (!data) throw createHttpError(404, 'No encontraste esta conversación.', 'messaging_not_found')
  return data
}

const getMyParticipant = async (context, conversationId) => {
  const { data, error } = await context.client
    .from('messaging_conversation_participants')
    .select('conversation_id, membership_id, joined_at, left_at, last_read_sequence, last_read_at')
    .eq('conversation_id', conversationId)
    .eq('membership_id', context.membershipId)
    .is('left_at', null)
    .maybeSingle()
  if (error) throw rpcError(error, 'messaging_participant_lookup_failed')
  return data
}

const getUnreadCount = async (context, conversationId, lastReadSequence) => {
  const { count, error } = await context.client
    .from('messaging_messages')
    .select('id', { count: 'exact', head: true })
    .eq('conversation_id', conversationId)
    .gt('sequence', lastReadSequence)
    .neq('sender_membership_id', context.membershipId)
  if (error) throw rpcError(error, 'messaging_unread_lookup_failed')
  return count ?? 0
}

const mapConversation = async (context, conversation, myParticipant, membersById) => {
  const unreadCount = await getUnreadCount(context, conversation.id, Number(myParticipant?.last_read_sequence ?? 0))
  const directPartnerId = conversation.conversation_type === 'direct'
    ? (conversation.direct_membership_low_id === context.membershipId
      ? conversation.direct_membership_high_id
      : conversation.direct_membership_low_id)
    : null

  return {
    id: conversation.id,
    household_id: conversation.household_id,
    type: conversation.conversation_type,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    last_activity_at: conversation.last_message_at ?? conversation.created_at,
    last_message: conversation.last_message_at ? {
      preview: conversation.last_message_preview,
      sender_membership_id: conversation.last_message_sender_membership_id,
      created_at: conversation.last_message_at,
    } : null,
    direct_partner: directPartnerId ? mapMember(membersById.get(directPartnerId)) : null,
    read_state: {
      last_read_sequence: Number(myParticipant?.last_read_sequence ?? 0),
      last_read_at: myParticipant?.last_read_at ?? null,
      unread_count: unreadCount,
    },
  }
}

const listConversations = async (context) => {
  await ensureHouseholdConversation(context)
  const { data: conversations, error } = await context.client
    .from('messaging_conversations')
    .select('*')
    .eq('household_id', context.householdId)
    .is('archived_at', null)
    .order('last_message_at', { ascending: false, nullsFirst: false })
    .order('created_at', { ascending: false })
  if (error) throw rpcError(error, 'messaging_conversations_list_failed')

  const rows = conversations ?? []
  const ids = rows.map((conversation) => conversation.id)
  const { data: participants, error: participantsError } = ids.length
    ? await context.client
      .from('messaging_conversation_participants')
      .select('conversation_id, membership_id, joined_at, left_at, last_read_sequence, last_read_at')
      .in('conversation_id', ids)
      .eq('membership_id', context.membershipId)
      .is('left_at', null)
    : { data: [], error: null }
  if (participantsError) throw rpcError(participantsError, 'messaging_participants_list_failed')
  const participantByConversationId = new Map((participants ?? []).map((item) => [item.conversation_id, item]))

  const memberIds = rows.flatMap((conversation) => [
    conversation.direct_membership_low_id,
    conversation.direct_membership_high_id,
  ])
  const membersById = await loadPublicMembers(context.client, memberIds)
  const mapped = await Promise.all(rows.map((conversation) => mapConversation(
    context,
    conversation,
    participantByConversationId.get(conversation.id) ?? null,
    membersById,
  )))
  return {
    conversations: mapped,
    unread_count: mapped.reduce((total, conversation) => total + conversation.read_state.unread_count, 0),
  }
}

const getConversation = async (context, conversationId) => {
  const conversation = await getConversationOrThrow(context, conversationId)
  const myParticipant = await getMyParticipant(context, conversationId)
  const membersById = await loadPublicMembers(context.client, [
    conversation.direct_membership_low_id,
    conversation.direct_membership_high_id,
  ])
  return { conversation: await mapConversation(context, conversation, myParticipant, membersById) }
}

const ensureDirectConversation = async (context, otherMembershipId) => {
  if (typeof otherMembershipId !== 'string' || !otherMembershipId) {
    throw createHttpError(400, 'Elegí a una persona válida.', 'messaging_invalid_direct_member')
  }
  const { data, error } = await context.client.rpc('messaging_ensure_direct_conversation', {
    p_household_id: context.householdId,
    p_other_membership_id: otherMembershipId,
  })
  if (error) throw rpcError(error, 'messaging_direct_ensure_failed')
  return getConversation(context, data)
}

const listMessages = async (context, conversationId, query = {}) => {
  await getConversationOrThrow(context, conversationId)
  const limit = parsePageSize(query.limit)
  const beforeSequence = query.before_sequence ? Number.parseInt(String(query.before_sequence), 10) : null
  if (beforeSequence !== null && (!Number.isInteger(beforeSequence) || beforeSequence < 1)) {
    throw createHttpError(400, 'El cursor no es válido.', 'messaging_invalid_cursor')
  }
  let request = context.client
    .from('messaging_messages')
    .select('*')
    .eq('conversation_id', conversationId)
    .order('sequence', { ascending: false })
    .limit(limit + 1)
  if (beforeSequence !== null) request = request.lt('sequence', beforeSequence)
  const { data, error } = await request
  if (error) throw rpcError(error, 'messaging_messages_list_failed')
  const page = data ?? []
  const hasMore = page.length > limit
  const rows = hasMore ? page.slice(0, limit) : page
  const [membersById, reactionsByMessageId, attachmentsByMessageId] = await Promise.all([
    loadPublicMembers(context.client, rows.map((message) => message.sender_membership_id)),
    loadReactions(context.client, rows.map((message) => message.id), context.membershipId),
    loadAttachments(context.client, rows.map((message) => message.id)),
  ])
  return {
    messages: rows.reverse().map((message) => mapMessage(message, membersById, reactionsByMessageId, attachmentsByMessageId)),
    page: { has_more: hasMore, next_before_sequence: hasMore ? Number(rows[rows.length - 1]?.sequence) : null },
  }
}

const sendMessage = async (context, conversationId, payload = {}) => {
  if (payload.type === 'task') {
    if (typeof payload.context_entity_id !== 'string' || !payload.context_entity_id) {
      throw createHttpError(400, 'Elegí una tarea válida.', 'messaging_invalid_task_reference')
    }
    if (typeof payload.client_message_id !== 'string' || !payload.client_message_id) {
      throw createHttpError(400, 'Falta el identificador del mensaje.', 'messaging_missing_client_message_id')
    }
    const { data, error } = await context.client.rpc('messaging_send_task_message', {
      p_conversation_id: conversationId,
      p_task_id: payload.context_entity_id,
      p_client_message_id: payload.client_message_id,
    })
    if (error) throw rpcError(error, 'messaging_task_send_failed')
    const membersById = await loadPublicMembers(context.client, [data.sender_membership_id])
    return { message: mapMessage(data, membersById) }
  }
  if (payload.type !== undefined && payload.type !== 'text') {
    if (!['image', 'audio', 'file'].includes(payload.type) || typeof payload.attachment_id !== 'string') {
      throw createHttpError(400, 'Este tipo de mensaje todavía no está disponible.', 'messaging_unsupported_type')
    }
    if (typeof payload.client_message_id !== 'string' || !payload.client_message_id) {
      throw createHttpError(400, 'Falta el identificador del mensaje.', 'messaging_missing_client_message_id')
    }
    const { data: requestedAttachment, error: attachmentError } = await context.client
      .from('messaging_attachments').select('id, attachment_kind, conversation_id')
      .eq('id', payload.attachment_id).eq('conversation_id', conversationId).maybeSingle()
    if (attachmentError) throw rpcError(attachmentError, 'messaging_attachment_lookup_failed')
    if (!requestedAttachment || requestedAttachment.attachment_kind !== payload.type) {
      throw createHttpError(400, 'El tipo de adjunto no coincide.', 'messaging_attachment_type_mismatch')
    }
    const { data, error } = await context.client.rpc('messaging_send_attachment_message', {
      p_conversation_id: conversationId,
      p_attachment_id: payload.attachment_id,
      p_client_message_id: payload.client_message_id,
    })
    if (error) throw rpcError(error, 'messaging_attachment_send_failed')
    const [membersById, attachmentsByMessageId] = await Promise.all([
      loadPublicMembers(context.client, [data.sender_membership_id]),
      loadAttachments(context.client, [data.id]),
    ])
    return { message: mapMessage(data, membersById, new Map(), attachmentsByMessageId) }
  }
  if (typeof payload.client_message_id !== 'string' || !payload.client_message_id) {
    throw createHttpError(400, 'Falta el identificador del mensaje.', 'messaging_missing_client_message_id')
  }
  const { data, error } = await context.client.rpc('messaging_send_text_message', {
    p_conversation_id: conversationId,
    p_body: payload.body,
    p_client_message_id: payload.client_message_id,
  })
  if (error) throw rpcError(error, 'messaging_send_failed')
  const membersById = await loadPublicMembers(context.client, [data.sender_membership_id])
  return { message: mapMessage(data, membersById) }
}

const markConversationRead = async (context, conversationId, payload = {}) => {
  const throughSequence = Number(payload.through_sequence)
  if (!Number.isInteger(throughSequence) || throughSequence < 0) {
    throw createHttpError(400, 'La posición de lectura no es válida.', 'messaging_invalid_read_cursor')
  }
  const { data, error } = await context.client.rpc('messaging_mark_conversation_read', {
    p_conversation_id: conversationId,
    p_through_sequence: throughSequence,
  })
  if (error) throw rpcError(error, 'messaging_mark_read_failed')
  return { read_state: {
    last_read_sequence: Number(data.last_read_sequence),
    last_read_at: data.last_read_at,
  } }
}

const toggleReaction = async (context, messageId, payload = {}) => {
  if (typeof payload.reaction_type !== 'string') {
    throw createHttpError(400, 'Elegí una reacción válida.', 'messaging_invalid_reaction')
  }
  const { data, error } = await context.client.rpc('messaging_toggle_reaction', {
    p_message_id: messageId,
    p_reaction_type: payload.reaction_type,
  })
  if (error) throw rpcError(error, 'messaging_reaction_failed')
  return { state: data }
}

module.exports = {
  listConversations,
  getConversation,
  ensureDirectConversation,
  listMessages,
  sendMessage,
  markConversationRead,
  toggleReaction,
}
