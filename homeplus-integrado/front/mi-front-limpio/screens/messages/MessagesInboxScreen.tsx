import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import { AppAvatar, AppScreen, AppText, EmptyState, ErrorState, IconButton, InteractivePressable } from '../../components/ui';
import { layout, radius, spacing } from '../../constants/theme';
import { HomePlusIcon } from '../../constants/icons';
import { useMessaging } from '../../context/MessagingContext';
import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import { getHouseholdMembers, type FamilyMember } from '../../services/family';
import type { Conversation } from '../../services/messages';

const activityLabel = (timestamp: string) => {
  const date = new Date(timestamp);
  const now = new Date();
  if (date.toDateString() === now.toDateString()) return date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
  return date.toLocaleDateString('es-AR', { day: 'numeric', month: 'short' });
};

const conversationLabel = (conversation: Conversation, householdName: string) => (
  conversation.type === 'household' ? householdName : conversation.direct_partner?.display_name ?? 'Conversación directa'
);

export function MessagesInboxScreen() {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const navigation = useNavigation<any>();
  const { session, authMe } = useAuth();
  const { currentHousehold } = useHousehold();
  const { orderedConversations, loadingInbox, inboxError, refreshInbox, ensureDirect } = useMessaging();
  const [chooserOpen, setChooserOpen] = useState(false);
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const householdId = currentHousehold?.id ?? authMe?.active_household?.id ?? null;
  const myMembershipId = authMe?.memberships.find((item) => item.household_id === householdId && item.status === 'active')?.id ?? null;
  const householdName = authMe?.active_household?.name ?? 'Hogar';

  const loadMembers = useCallback(async () => {
    if (!session?.access_token || !householdId) return;
    setMembersLoading(true);
    try {
      const response = await getHouseholdMembers(session.access_token, householdId);
      setMembers(response.members.filter((member) => member.status === 'active' && member.membership_id !== myMembershipId));
    } finally { setMembersLoading(false); }
  }, [householdId, myMembershipId, session?.access_token]);

  useEffect(() => { if (chooserOpen) void loadMembers(); }, [chooserOpen, loadMembers]);

  const openConversation = (conversation: Conversation) => navigation.navigate('MessagesConversation', { conversationId: conversation.id });
  const startDirect = async (member: FamilyMember) => {
    setOpeningId(member.membership_id);
    try {
      const { id } = await ensureDirect(member.membership_id);
      setChooserOpen(false);
      navigation.navigate('MessagesConversation', { conversationId: id });
    } finally { setOpeningId(null); }
  };

  const hasConversations = orderedConversations.length > 0;
  const visibleMembers = useMemo(() => members, [members]);
  const householdConversations = orderedConversations.filter((conversation) => conversation.type === 'household');
  const directConversations = orderedConversations.filter((conversation) => conversation.type === 'direct');

  return (
    <AppScreen scroll={false} padded={false} bottomInset="none" background="base">
      <View testID="header.messages" style={styles.header}>
        <IconButton icon="chevron-back" variant="plain" onPress={() => navigation.goBack()} accessibilityLabel="Volver" />
        <AppText variant="body" weight="800" style={styles.headerTitle}>Mensajes</AppText>
        <IconButton icon="create" variant="plain" onPress={() => setChooserOpen(true)} accessibilityLabel="Iniciar mensaje directo" />
      </View>

      {loadingInbox && !hasConversations ? <View style={styles.center}><ActivityIndicator color={colors.brand} size="large" /></View> : null}
      {!loadingInbox && inboxError && !hasConversations ? <ErrorState title="No pudimos cargar Mensajes" description={inboxError} onRetry={() => void refreshInbox()} /> : null}
      {!loadingInbox && !inboxError && !hasConversations ? <EmptyState illustration={<HomePlusIcon name="chatbubble-ellipses-outline" size={32} color={colors.brand} />} title="Todavía no hay conversaciones" description="El chat principal de tu hogar aparecerá aquí." actionLabel="Actualizar" onAction={() => void refreshInbox()} /> : null}
      {hasConversations ? (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={loadingInbox} onRefresh={() => void refreshInbox()} tintColor={colors.brand} />}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.intro}>
            <AppText variant="title1">Mensajes</AppText>
            <AppText variant="bodySmall" tone="secondary">Conversaciones que ayudan a mover la casa</AppText>
          </View>
          {householdConversations.length > 0 ? <AppText variant="caption" weight="800" tone="tertiary" style={styles.sectionLabel}>HOGAR</AppText> : null}
          {householdConversations.map((conversation) => {
            const title = conversationLabel(conversation, householdName);
            const preview = conversation.last_message?.preview ?? (conversation.type === 'household' ? 'Escribí el primer mensaje para tu hogar.' : 'Todavía no hay mensajes.');
            return (
              <InteractivePressable key={conversation.id} testID="messages.conversation.household" style={[styles.row, styles.householdRow]} onPress={() => openConversation(conversation)} accessibilityLabel={`Abrir ${title}${conversation.read_state.unread_count > 0 ? `, ${conversation.read_state.unread_count > 99 ? 'más de 99' : conversation.read_state.unread_count} ${conversation.read_state.unread_count === 1 ? 'mensaje sin leer' : 'mensajes sin leer'}` : ''}`}>
                <View style={styles.householdAvatar}><HomePlusIcon name="people-outline" size={21} color={colors.terracotta[500]} /></View>
                <View style={styles.rowCopy}>
                  <View style={styles.rowTitle}><AppText variant="body" weight={conversation.read_state.unread_count > 0 ? '800' : '700'} numberOfLines={1}>{title}</AppText><AppText variant="caption" tone="tertiary">{activityLabel(conversation.last_activity_at)}</AppText></View>
                  <View style={styles.rowPreview}><AppText variant="bodySmall" tone={conversation.read_state.unread_count > 0 ? 'primary' : 'secondary'} weight={conversation.read_state.unread_count > 0 ? '700' : '500'} numberOfLines={1}>{preview}</AppText>{conversation.read_state.unread_count > 0 ? <View style={styles.unread}><AppText variant="micro" tone="inverse" weight="800">{conversation.read_state.unread_count > 99 ? '99+' : conversation.read_state.unread_count}</AppText></View> : null}</View>
                </View>
              </InteractivePressable>
            );
          })}
          {directConversations.length > 0 ? <AppText variant="caption" weight="800" tone="tertiary" style={styles.sectionLabel}>DIRECTOS</AppText> : null}
          {directConversations.length > 0 ? <View style={styles.directGroup}>{directConversations.map((conversation) => {
            const title = conversationLabel(conversation, householdName);
            const preview = conversation.last_message?.preview ?? 'Todavía no hay mensajes.';
            return <InteractivePressable key={conversation.id} testID={`messages.conversation.direct.${conversation.id}`} style={styles.row} onPress={() => openConversation(conversation)} accessibilityLabel={`Abrir ${title}${conversation.read_state.unread_count > 0 ? `, ${conversation.read_state.unread_count > 99 ? 'más de 99' : conversation.read_state.unread_count} ${conversation.read_state.unread_count === 1 ? 'mensaje sin leer' : 'mensajes sin leer'}` : ''}`}>
              <AppAvatar size="md" name={title} imageUrl={conversation.direct_partner?.avatar_url} />
              <View style={styles.rowCopy}>
                <View style={styles.rowTitle}><AppText variant="body" weight={conversation.read_state.unread_count > 0 ? '800' : '700'} numberOfLines={1}>{title}</AppText><AppText variant="caption" tone="tertiary">{activityLabel(conversation.last_activity_at)}</AppText></View>
                <View style={styles.rowPreview}><AppText variant="bodySmall" tone={conversation.read_state.unread_count > 0 ? 'primary' : 'secondary'} weight={conversation.read_state.unread_count > 0 ? '700' : '500'} numberOfLines={1}>{preview}</AppText>{conversation.read_state.unread_count > 0 ? <View style={styles.unread}><AppText variant="micro" tone="inverse" weight="800">{conversation.read_state.unread_count > 99 ? '99+' : conversation.read_state.unread_count}</AppText></View> : null}</View>
              </View>
            </InteractivePressable>;
          })}</View> : null}
        </ScrollView>
      ) : null}

      <Modal visible={chooserOpen} transparent animationType="slide" onRequestClose={() => setChooserOpen(false)}>
        <Pressable style={styles.modalScrim} onPress={() => setChooserOpen(false)} accessibilityRole="button" accessibilityLabel="Cerrar nuevo mensaje">
          <Pressable style={styles.sheet} onPress={(event) => event.stopPropagation()} accessibilityRole="none">
            <View style={styles.sheetHeader}><View><AppText variant="title3">Nuevo mensaje</AppText><AppText variant="bodySmall" tone="secondary">Elegí a alguien de tu hogar.</AppText></View><IconButton icon="close" variant="plain" onPress={() => setChooserOpen(false)} accessibilityLabel="Cerrar" /></View>
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.memberList}>
              {membersLoading ? <ActivityIndicator color={colors.brand} /> : visibleMembers.map((member) => <InteractivePressable key={member.membership_id} style={styles.memberRow} onPress={() => void startDirect(member)} disabled={openingId !== null} accessibilityLabel={`Enviar mensaje a ${member.display_name}`}><AppAvatar name={member.display_name} imageUrl={member.avatar_url} size="md" /><AppText variant="body" weight="700" style={styles.memberName}>{member.display_name}</AppText>{openingId === member.membership_id ? <ActivityIndicator color={colors.brand} /> : <HomePlusIcon name="chevron-forward" size={20} color={colors.text.tertiary} />}</InteractivePressable>)}
              {!membersLoading && visibleMembers.length === 0 ? <AppText variant="bodySmall" tone="secondary" align="center">No hay otra persona activa en este hogar.</AppText> : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </AppScreen>
  );
}



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: layout.screen.horizontalPadding, paddingTop: layout.screen.topPadding, paddingBottom: spacing[2] },
  headerTitle: { flex: 1, marginLeft: spacing[1] },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list: { width: '100%', maxWidth: layout.screen.contentMaxWidth, alignSelf: 'center', paddingHorizontal: layout.screen.horizontalPadding, paddingBottom: layout.screen.bottomPadding }, intro: { gap: layout.stack.related, marginTop: layout.screen.topPadding, marginBottom: layout.stack.section }, sectionLabel: { marginTop: spacing[2], marginBottom: layout.stack.related, letterSpacing: 0.6 },
  row: { minHeight: 68, flexDirection: 'row', gap: spacing[3], alignItems: 'center', paddingHorizontal: spacing[4], paddingVertical: spacing[3], borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border.subtle }, householdRow: { marginBottom: spacing[3], borderWidth: 1, borderRadius: radius.xl, borderColor: colors.border.subtle, backgroundColor: colors.surface.card }, directGroup: { overflow: 'hidden', borderWidth: 1, borderRadius: radius.xl, borderColor: colors.border.subtle, backgroundColor: colors.surface.card },
  householdAvatar: { width: 44, height: 44, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.terracotta[50] },
  rowCopy: { flex: 1, gap: 3 }, rowTitle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing[2] }, rowPreview: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] },
  unread: { minWidth: 19, height: 19, paddingHorizontal: 5, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand },
  modalScrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: colors.surface.overlay },
  sheet: { width: '100%', maxWidth: 560, maxHeight: '72%', alignSelf: 'center', paddingTop: spacing[4], paddingHorizontal: layout.screen.horizontalPadding, paddingBottom: spacing[7], borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, backgroundColor: colors.background.base },
  sheetHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing[3] }, memberList: { gap: spacing[1] },
  memberRow: { minHeight: 58, flexDirection: 'row', alignItems: 'center', gap: spacing[3], paddingVertical: spacing[2] }, memberName: { flex: 1 },
});
}
