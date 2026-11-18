import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, FlatList, Image, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, TextInput, View, type NativeScrollEvent, type NativeSyntheticEvent } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppAvatar, AppText, IconButton } from '../../components/ui';
import { colors, layout, radius, spacing } from '../../constants/theme';
import { HomePlusIcon } from '../../constants/icons';
import { useAuth } from '../../context/AuthContext';
import { useMessaging } from '../../context/MessagingContext';
import { linkMessageToTask, type Message } from '../../services/messages';
import { createPlannerTask, listPlannerTasks, type PlannerTask } from '../../services/plannerTasks';
import { pickMessageFile, pickMessageImage, type LocalMessageMedia } from '../../services/richMessagingMedia';
import { MessageAudioRecorder } from '../../components/messages/MessageAudioRecorder';
import { MessageRenderer } from '../../components/messages/MessageRenderer';

const timeLabel = (timestamp: string) => new Date(timestamp).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
const EMPTY_MESSAGES: Message[] = [];

export function MessagesConversationScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const insets = useSafeAreaInsets();
  const conversationId = route.params.conversationId as string;
  const { authMe, session } = useAuth();
  const { conversationsById, messagesByConversationId, loadMessages, sendTextMessage, sendTaskMessage, sendMediaMessage, markRead, toggleReaction, subscribeConversation } = useMessaging();
  const [draft, setDraft] = useState('');
  const [actionSheetOpen, setActionSheetOpen] = useState(false);
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [shareTasks, setShareTasks] = useState<PlannerTask[]>([]);
  const [audioRecorderOpen, setAudioRecorderOpen] = useState(false);
  const [messageAction, setMessageAction] = useState<Message | null>(null);
  const [taskTitle, setTaskTitle] = useState('');
  const [creatingTask, setCreatingTask] = useState(false);
  const [taskCreationError, setTaskCreationError] = useState<string | null>(null);
  const [createdTask, setCreatedTask] = useState<{ id: string; title: string } | null>(null);
  const [hasNewMessagesBelow, setHasNewMessagesBelow] = useState(false);
  const [pendingMedia, setPendingMedia] = useState<LocalMessageMedia | null>(null);
  const listRef = useRef<FlatList<Message>>(null);
  const previousMessageCount = useRef(0);
  const isNearBottom = useRef(true);
  const conversation = conversationsById[conversationId];
  const myMembershipId = authMe?.memberships.find((item) => item.household_id === conversation?.household_id && item.status === 'active')?.id ?? null;
  const messages = messagesByConversationId[conversationId] ?? EMPTY_MESSAGES;
  const title = conversation?.type === 'household' ? (authMe?.active_household?.name ?? 'Hogar') : (conversation?.direct_partner?.display_name ?? 'Mensajes');

  useEffect(() => { void loadMessages(conversationId); return subscribeConversation(conversationId); }, [conversationId, loadMessages, subscribeConversation]);
  useEffect(() => {
    previousMessageCount.current = 0;
    isNearBottom.current = true;
    setHasNewMessagesBelow(false);
    setCreatedTask(null);
  }, [conversationId]);
  useEffect(() => {
    const latestIncoming = [...messages].reverse().find((message) => message.sender_membership_id !== myMembershipId && message.delivery !== 'sending');
    if (latestIncoming) void markRead(conversationId, latestIncoming.sequence);
  }, [conversationId, markRead, messages, myMembershipId]);
  useEffect(() => {
    const previousCount = previousMessageCount.current;
    previousMessageCount.current = messages.length;
    if (!messages.length || messages.length <= previousCount) return;

    const latest = messages[messages.length - 1];
    const shouldFollow = previousCount === 0
      || isNearBottom.current
      || latest.sender_membership_id === myMembershipId;

    if (shouldFollow) {
      setHasNewMessagesBelow(false);
      requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: previousCount > 0 }));
      return;
    }

    setHasNewMessagesBelow(true);
  }, [messages, myMembershipId]);
  useEffect(() => { if (taskPickerOpen && session?.access_token) void listPlannerTasks(session.access_token, { status: 'pending', limit: 40 }).then(({ tasks }) => setShareTasks(tasks)).catch(() => setShareTasks([])); }, [session?.access_token, taskPickerOpen]);

  const headerAvatar = conversation?.type === 'direct' ? <AppAvatar size="sm" name={title} imageUrl={conversation.direct_partner?.avatar_url} /> : <View style={styles.headerHome}><HomePlusIcon name="home" size={17} color={colors.text.inverse} /></View>;
  const submit = () => { const body = draft.trim(); if (!body) return; setDraft(''); void sendTextMessage(conversationId, body); };
  const attach = async (picker: () => Promise<LocalMessageMedia | null>) => {
    setActionSheetOpen(false);
    try { const media = await picker(); if (media) setPendingMedia(media); } catch { /* permission failures keep the composer functional */ }
  };
  const handleMessageScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const distanceFromBottom = contentSize.height - (contentOffset.y + layoutMeasurement.height);
    const nextIsNearBottom = distanceFromBottom < 96;
    isNearBottom.current = nextIsNearBottom;
    if (nextIsNearBottom && hasNewMessagesBelow) setHasNewMessagesBelow(false);
  };
  const revealLatestMessages = () => {
    isNearBottom.current = true;
    setHasNewMessagesBelow(false);
    listRef.current?.scrollToEnd({ animated: true });
  };
  const createTaskFromMessage = async () => {
    if (!session?.access_token || !messageAction || !taskTitle.trim()) return;
    setTaskCreationError(null);
    setCreatingTask(true);
    try {
      const response = await createPlannerTask(session.access_token, {
        title: taskTitle.trim(),
        description: messageAction.type === 'text' ? messageAction.body : `Creada desde un mensaje ${messageAction.type} de HomePlus.`,
      });
      await linkMessageToTask(session.access_token, messageAction.id, response.task.id);
      setCreatedTask({ id: response.task.id, title: response.task.title });
      AccessibilityInfo.announceForAccessibility(`Tarea creada: ${response.task.title}`);
      setMessageAction(null); setTaskTitle('');
    } catch {
      setTaskCreationError('No pudimos crear la tarea. Revisá tu conexión e intentá nuevamente.');
    } finally { setCreatingTask(false); }
  };

  return <KeyboardAvoidingView testID="screen.messages.conversation" style={styles.page} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <View style={[styles.header, { paddingTop: insets.top + spacing[2] }]}>
      <IconButton icon="chevron-back" variant="plain" onPress={() => navigation.goBack()} accessibilityLabel="Volver a Mensajes" />
      {headerAvatar}<View style={styles.headerCopy}><AppText variant="body" weight="800" numberOfLines={1}>{title}</AppText><AppText variant="caption" tone="secondary">{conversation?.type === 'household' ? 'Chat principal del hogar' : 'Mensaje directo'}</AppText></View>
    </View>
    <FlatList ref={listRef} data={messages} keyExtractor={(item) => item.id} contentContainerStyle={styles.messages} onScroll={handleMessageScroll} scrollEventThrottle={32} renderItem={({ item }) => {
      const mine = item.sender_membership_id === myMembershipId;
      const retry = () => {
        if (item.delivery !== 'failed') return;
        if (item.type === 'task' && item.context_entity_id) {
          void sendTaskMessage(conversationId, item.context_entity_id, item.client_message_id);
          return;
        }
        const attachment = item.attachments?.[0];
        if (attachment?.local_uri) {
          void sendMediaMessage(conversationId, {
            uri: attachment.local_uri, kind: attachment.kind, mimeType: attachment.mime_type,
            originalName: attachment.original_name, sizeBytes: attachment.size_bytes, width: attachment.width,
            height: attachment.height, durationMs: attachment.duration_ms,
          }, item.client_message_id, attachment.id.replace('pending:', ''));
          return;
        }
        void sendTextMessage(conversationId, item.body, item.client_message_id);
      };
      const react = () => {
        if (item.delivery !== 'sent') return;
        setTaskCreationError(null);
        setMessageAction(item);
        setTaskTitle(item.type === 'text' ? item.body.slice(0, 140) : 'Nueva tarea');
      };
      const likes = item.reactions?.find((reaction) => reaction.reaction_type === 'like');
      return <Pressable onPress={retry} onLongPress={react} style={[styles.messageRow, mine ? styles.messageMine : styles.messageTheirs]} accessibilityLabel={item.delivery === 'failed' ? 'Mensaje no enviado. Tocá para reintentar.' : 'Mantené presionado para reaccionar'}>
        <View style={styles.messageCluster}>
          {!mine && item.sender?.display_name ? <AppText variant="caption" tone="tertiary" style={styles.senderName}>{item.sender.display_name}</AppText> : null}
          <MessageRenderer message={item} mine={mine} accessToken={session?.access_token ?? null} />
          <View style={styles.meta}><AppText variant="micro" tone="tertiary">{item.delivery === 'sending' ? 'Enviando…' : item.delivery === 'failed' ? 'No enviado · Reintentar' : timeLabel(item.created_at)}</AppText></View>
          {likes ? <View style={[styles.reaction, likes.mine && styles.reactionMine]}><AppText variant="micro">♡ {likes.count}</AppText></View> : null}
        </View>
      </Pressable>;
    }} ListEmptyComponent={<View style={styles.empty}><AppText variant="title3">Una conversación para el hogar</AppText><AppText variant="bodySmall" tone="secondary" align="center">Escribí para empezar. Más adelante, desde acá podrán nacer acciones de HomePlus.</AppText></View>} />
    {hasNewMessagesBelow ? <View style={styles.newMessagesRow}><Pressable testID="messages.newMessages" onPress={revealLatestMessages} accessibilityRole="button" accessibilityLabel="Ver mensajes nuevos" style={({ pressed }) => [styles.newMessagesButton, pressed && styles.inlinePressed]}><HomePlusIcon name="arrow-down" size={16} color={colors.brandPressed} /><AppText variant="caption" tone="brand" weight="800">Nuevos mensajes</AppText></Pressable></View> : null}
    {createdTask ? <View testID="messages.taskCreated" accessibilityRole="alert" style={styles.taskCreatedBanner}><View style={styles.taskCreatedCopy}><HomePlusIcon name="checkmark-circle" size={20} color={colors.success.base} /><View style={{ flex: 1 }}><AppText variant="bodySmall" weight="800">Tarea creada</AppText><AppText variant="caption" tone="secondary" numberOfLines={1}>{createdTask.title}</AppText></View></View><Pressable testID="messages.taskCreated.open" accessibilityRole="button" accessibilityLabel={`Ver tarea ${createdTask.title}`} onPress={() => { const task = createdTask; setCreatedTask(null); navigation.navigate('TaskDetailFromMessage', { entityId: task.id, source: 'messages', returnTo: 'previous' }); }} style={({ pressed }) => [styles.taskCreatedAction, pressed && styles.inlinePressed]}><AppText variant="caption" tone="brand" weight="800">Ver tarea</AppText></Pressable><Pressable accessibilityRole="button" accessibilityLabel="Cerrar confirmación de tarea" onPress={() => setCreatedTask(null)} style={({ pressed }) => [styles.taskCreatedClose, pressed && styles.inlinePressed]}><HomePlusIcon name="close" size={18} color={colors.text.tertiary} /></Pressable></View> : null}
    <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, spacing[3]) }]}>
      <View testID="messages.attach"><Pressable testID="messages.action.add" onPress={() => setActionSheetOpen(true)} accessibilityRole="button" accessibilityLabel="Adjuntar o crear una acción" style={({ pressed }) => [styles.add, pressed && styles.addPressed]}><HomePlusIcon name="add" size={22} color={colors.brand} /></Pressable></View>
      <TextInput testID="messages.composer.input" value={draft} onChangeText={setDraft} placeholder="Escribí un mensaje" placeholderTextColor={colors.text.muted} multiline maxLength={4000} style={styles.input} accessibilityLabel="Mensaje" />
      <Pressable testID="messages.composer.send" onPress={submit} disabled={!draft.trim()} accessibilityRole="button" accessibilityLabel="Enviar mensaje" style={({ pressed }) => [styles.send, !draft.trim() && styles.sendDisabled, pressed && styles.sendPressed]}><HomePlusIcon name="arrow-up" size={20} color={colors.text.inverse} /></Pressable>
    </View>
    <Modal visible={actionSheetOpen} transparent animationType="slide" onRequestClose={() => setActionSheetOpen(false)}>
      <Pressable style={styles.sheetScrim} onPress={() => setActionSheetOpen(false)} accessibilityRole="button" accessibilityLabel="Cerrar acciones">
        <Pressable testID="messages.action.sheet" style={[styles.actionSheet, { paddingBottom: Math.max(insets.bottom, spacing[4]) }]} onPress={(event) => event.stopPropagation()}>
          <View style={styles.sheetHandle} />
          <AppText variant="title3">Compartir en la conversación</AppText>
          <ScrollView contentContainerStyle={styles.actionGrid} showsVerticalScrollIndicator={false}>
            <Pressable testID="messages.attach.photo" onPress={() => void attach(() => pickMessageImage('gallery'))} accessibilityRole="button" accessibilityLabel="Elegir foto" style={({ pressed }) => [styles.actionOption, pressed && styles.actionOptionPressed]}><View style={styles.actionIcon}><HomePlusIcon name="image-outline" size={20} color={colors.brand} /></View><AppText variant="bodySmall" weight="800">Foto</AppText><AppText variant="caption" tone="secondary">Galería</AppText></Pressable>
            <Pressable testID="messages.attach.camera" onPress={() => void attach(() => pickMessageImage('camera'))} accessibilityRole="button" accessibilityLabel="Sacar foto" style={({ pressed }) => [styles.actionOption, pressed && styles.actionOptionPressed]}><View style={styles.actionIcon}><HomePlusIcon name="camera-outline" size={20} color={colors.brand} /></View><AppText variant="bodySmall" weight="800">Cámara</AppText><AppText variant="caption" tone="secondary">Sacar foto</AppText></Pressable>
            <Pressable testID="messages.attach.audio" onPress={() => { setActionSheetOpen(false); setAudioRecorderOpen(true); }} accessibilityRole="button" accessibilityLabel="Grabar audio" style={({ pressed }) => [styles.actionOption, pressed && styles.actionOptionPressed]}><View style={styles.actionIcon}><HomePlusIcon name="mic-outline" size={20} color={colors.brand} /></View><AppText variant="bodySmall" weight="800">Audio</AppText><AppText variant="caption" tone="secondary">Nota de voz</AppText></Pressable>
            <Pressable testID="messages.attach.file" onPress={() => void attach(pickMessageFile)} accessibilityRole="button" accessibilityLabel="Adjuntar archivo" style={({ pressed }) => [styles.actionOption, pressed && styles.actionOptionPressed]}><View style={styles.actionIcon}><HomePlusIcon name="document-outline" size={20} color={colors.brand} /></View><AppText variant="bodySmall" weight="800">Archivo</AppText><AppText variant="caption" tone="secondary">Adjuntar documento</AppText></Pressable>
            <Pressable testID="messages.action.tarea" onPress={() => { setActionSheetOpen(false); setTaskPickerOpen(true); }} accessibilityRole="button" accessibilityLabel="Elegir tarea para compartir" style={({ pressed }) => [styles.actionOption, pressed && styles.actionOptionPressed]}><View style={styles.actionIcon}><HomePlusIcon name="checkbox-outline" size={20} color={colors.brand} /></View><AppText variant="bodySmall" weight="800">Tarea</AppText><AppText variant="caption" tone="secondary">Compartir tarea</AppText></Pressable>
            {[['Plan', 'messages.action.plan'], ['Compra', 'messages.action.compra'], ['Lugar', 'messages.action.lugar'], ['Archivo contextual', 'messages.action.archivo']].map(([label, testID]) => <Pressable key={label} testID={testID} disabled accessibilityState={{ disabled: true }} accessibilityLabel={`${label}. Próximamente`} style={[styles.actionOption, styles.actionDisabled]}><AppText variant="bodySmall" weight="800">{label}</AppText><AppText variant="caption" tone="secondary">Próximamente</AppText></Pressable>)}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
    <Modal visible={taskPickerOpen} transparent animationType="slide" onRequestClose={() => setTaskPickerOpen(false)}><Pressable testID="messages.taskPicker" style={styles.sheetScrim} onPress={() => setTaskPickerOpen(false)} accessibilityRole="button" accessibilityLabel="Cerrar selector de tareas"><Pressable style={[styles.actionSheet, { paddingBottom: Math.max(insets.bottom, spacing[4]) }]} onPress={(event) => event.stopPropagation()} accessibilityRole="none"><View style={styles.sheetHandle} /><AppText variant="title3">Compartir tarea</AppText><ScrollView contentContainerStyle={styles.taskPicker}>{shareTasks.map((task, index) => <Pressable testID={index === 0 ? 'messages.taskPicker.firstTask' : undefined} key={task.id} style={styles.taskOption} onPress={() => { setTaskPickerOpen(false); void sendTaskMessage(conversationId, task.id); }} accessibilityLabel={`Compartir tarea ${task.title}`}><AppText variant="bodySmall" weight="800" numberOfLines={2}>{task.title}</AppText><AppText variant="caption" tone="secondary">{task.due_date ?? 'Sin fecha'} · {task.assigned_member?.display_name ?? 'Sin asignar'}</AppText></Pressable>)}</ScrollView></Pressable></Pressable></Modal>
    <Modal visible={audioRecorderOpen} transparent animationType="slide" onRequestClose={() => setAudioRecorderOpen(false)}><View style={styles.sheetScrim}><View style={[styles.actionSheet, { paddingBottom: Math.max(insets.bottom, spacing[4]) }]}><View style={styles.sheetHandle} /><MessageAudioRecorder onCancel={() => setAudioRecorderOpen(false)} onReady={(media) => { setAudioRecorderOpen(false); setPendingMedia(media); }} /></View></View></Modal>
    <Modal visible={Boolean(pendingMedia)} transparent animationType="slide" onRequestClose={() => setPendingMedia(null)}><View style={styles.sheetScrim}><View style={[styles.actionSheet, { paddingBottom: Math.max(insets.bottom, spacing[4]) }]}><View style={styles.sheetHandle} /><AppText variant="title3">Vista previa</AppText>{pendingMedia?.kind === 'image' ? <Image source={{ uri: pendingMedia.uri }} style={styles.previewImage} resizeMode="contain" accessibilityLabel="Vista previa de la foto"/> : <View style={styles.previewInfo}><HomePlusIcon name={pendingMedia?.kind === 'audio' ? 'mic-outline' : 'document-outline'} size={24} color={colors.brand}/><AppText weight="800">{pendingMedia?.originalName}</AppText><AppText tone="secondary">{pendingMedia?.kind === 'audio' ? 'Audio listo para enviar' : 'Archivo listo para enviar'}</AppText></View>}<View style={styles.previewActions}><Pressable onPress={() => setPendingMedia(null)} style={styles.previewCancel}><AppText weight="800">Cancelar</AppText></Pressable><Pressable testID="messages.media.send" onPress={() => { if (pendingMedia) void sendMediaMessage(conversationId, pendingMedia); setPendingMedia(null); }} style={styles.createTask}><AppText tone="inverse" weight="800">Enviar</AppText></Pressable></View></View></View></Modal>
    <Modal visible={Boolean(messageAction)} transparent animationType="slide" onRequestClose={() => { setMessageAction(null); setTaskCreationError(null); }}><View style={styles.sheetScrim}><View style={[styles.actionSheet, { paddingBottom: Math.max(insets.bottom, spacing[4]) }]}><View style={styles.sheetHandle} /><AppText variant="title3">Acciones del mensaje</AppText><Pressable onPress={() => messageAction && void toggleReaction(conversationId, messageAction.id, 'like')} style={styles.messageAction} accessibilityLabel="Reaccionar al mensaje"><AppText weight="800">Reaccionar</AppText></Pressable><AppText variant="bodySmall" weight="800">Convertir en acción</AppText><TextInput value={taskTitle} onChangeText={setTaskTitle} placeholder="Título de la tarea" style={styles.input} accessibilityLabel="Título de tarea"/>{taskCreationError ? <AppText testID="messages.action.createTask.error" variant="caption" tone="danger" accessibilityRole="alert">{taskCreationError}</AppText> : null}<Pressable testID="messages.action.createTask" onPress={() => void createTaskFromMessage()} disabled={!taskTitle.trim() || creatingTask} style={[styles.createTask, (!taskTitle.trim() || creatingTask) && styles.createTaskDisabled]} accessibilityLabel="Crear tarea desde mensaje"><AppText tone="inverse" weight="800">{creatingTask ? 'Creando…' : 'Crear tarea'}</AppText></Pressable></View></View></Modal>
  </KeyboardAvoidingView>;
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background.base }, header: { flexDirection: 'row', alignItems: 'center', gap: spacing[2], paddingHorizontal: layout.screen.horizontalPadding, paddingBottom: spacing[3], borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border.subtle },
  headerHome: { width: 36, height: 36, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.sage[600] }, headerCopy: { flex: 1, gap: 1 },
  messages: { flexGrow: 1, width: '100%', maxWidth: layout.screen.contentMaxWidth, alignSelf: 'center', paddingHorizontal: layout.screen.horizontalPaddingCompact, paddingVertical: layout.stack.content, gap: layout.stack.component }, empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: layout.stack.related, paddingHorizontal: layout.screen.horizontalPaddingWide },
  messageRow: { flexDirection: 'row' }, messageMine: { justifyContent: 'flex-end' }, messageTheirs: { justifyContent: 'flex-start' }, messageCluster: { maxWidth: '84%' }, senderName: { marginLeft: spacing[2], marginBottom: 3 }, bubble: { borderRadius: radius.xl, paddingHorizontal: spacing[3], paddingTop: spacing[2], paddingBottom: spacing[1] }, bubbleMine: { backgroundColor: colors.terracotta[600], borderBottomRightRadius: 5 }, bubbleTheirs: { borderWidth: 1, borderColor: colors.border.subtle, backgroundColor: colors.surface.card, borderBottomLeftRadius: 5 }, meta: { alignItems: 'flex-end', marginTop: 3 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: spacing[2], paddingTop: spacing[2], paddingHorizontal: layout.screen.horizontalPaddingCompact, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border.subtle, backgroundColor: colors.surface.card }, input: { flex: 1, maxHeight: 112, minHeight: 46, borderWidth: 1, borderColor: colors.border.default, borderRadius: radius.pill, paddingHorizontal: spacing[4], paddingVertical: spacing[2], color: colors.text.primary, textAlignVertical: 'center' }, add: { width: 48, height: 48, borderWidth: 1, borderColor: colors.border.default, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' }, addPressed: { opacity: 0.68 }, send: { width: 46, height: 46, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand }, sendDisabled: { backgroundColor: colors.text.muted }, sendPressed: { opacity: 0.82 },
  newMessagesRow: { alignItems: 'center', paddingVertical: spacing[1], backgroundColor: colors.background.base }, newMessagesButton: { minHeight: 40, flexDirection: 'row', alignItems: 'center', gap: spacing[1], paddingHorizontal: spacing[4], borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border.subtle, backgroundColor: colors.surface.card }, inlinePressed: { opacity: 0.82 },
  taskCreatedBanner: { minHeight: 60, flexDirection: 'row', alignItems: 'center', gap: spacing[2], paddingHorizontal: layout.screen.horizontalPaddingCompact, paddingVertical: spacing[2], borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.success.base, backgroundColor: colors.success.soft }, taskCreatedCopy: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: spacing[2] }, taskCreatedAction: { minWidth: 72, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing[2] }, taskCreatedClose: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.pill },
  sheetScrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: colors.surface.overlay }, actionSheet: { width: '100%', maxWidth: 600, maxHeight: '74%', alignSelf: 'center', paddingTop: spacing[2], paddingHorizontal: layout.screen.horizontalPadding, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, backgroundColor: colors.background.base }, sheetHandle: { alignSelf: 'center', width: 38, height: 4, borderRadius: radius.pill, marginBottom: spacing[2], backgroundColor: colors.border.default }, actionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2], paddingTop: spacing[4] }, actionOption: { width: '48%', minHeight: 88, padding: spacing[3], borderWidth: 1, borderColor: colors.border.default, borderRadius: radius.lg, backgroundColor: colors.surface.card }, actionOptionPressed: { opacity: 0.86, backgroundColor: colors.surface.soft }, actionIcon: { width: 28, height: 28, marginBottom: spacing[1], borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.terracotta[50] },
  actionDisabled: { opacity: 0.45 }, taskPicker: { gap: spacing[1], paddingVertical: spacing[3] }, taskOption: { minHeight: 60, paddingVertical: spacing[2], borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border.subtle, gap: 3 },
  reaction: { alignSelf: 'flex-start', marginTop: spacing[1], paddingHorizontal: spacing[2], paddingVertical: 3, borderRadius: radius.pill, backgroundColor: colors.surface.soft, borderWidth: 1, borderColor: colors.border.subtle }, reactionMine: { borderColor: colors.terracotta[300] },
  messageAction: { minHeight: 48, justifyContent: 'center' }, createTask: { minHeight: 48, alignItems: 'center', justifyContent: 'center', borderRadius: radius.lg, backgroundColor: colors.brand, marginBottom: spacing[2] }, createTaskDisabled: { backgroundColor: colors.text.muted },
  previewImage: { width: '100%', height: 240, borderRadius: radius.lg, backgroundColor: colors.surface.soft }, previewInfo: { minHeight: 160, alignItems: 'center', justifyContent: 'center', gap: spacing[2], borderRadius: radius.lg, backgroundColor: colors.surface.soft }, previewActions: { flexDirection: 'row', gap: spacing[2] }, previewCancel: { minHeight: 48, flex: 1, alignItems: 'center', justifyContent: 'center', borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border.default },
});
