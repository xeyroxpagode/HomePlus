import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { AppText } from '../ui';
import { radius, spacing } from '../../constants/theme';
import { HomePlusIcon } from '../../constants/icons';
import { useAuth } from '../../context/AuthContext';
import { useAppRefresh } from '../../context/AppRefreshContext';
import { claimPlannerTaskV1, getPlannerTaskFulfillmentV1, getTaskById, type PlannerTask } from '../../services/plannerTasks';

export function MessageContextCard({ type, entityId }: { type: 'task'; entityId: string }) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const { session } = useAuth();
  const { plannerChangedAt, markPlannerChanged } = useAppRefresh();
  const navigation = useNavigation<any>();
  const [task, setTask] = useState<PlannerTask | null>(null);
  const [assignmentVersion, setAssignmentVersion] = useState<number | null>(null);
  const [claimAvailable, setClaimAvailable] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const load = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const [{ task: next }, fulfillment] = await Promise.all([getTaskById(session.access_token, entityId), getPlannerTaskFulfillmentV1(session.access_token, entityId)]);
      setTask(next);
      setAssignmentVersion(fulfillment.task.assignment.version);
      setClaimAvailable(fulfillment.task.availableActions.some((action) => action.action === 'claim'));
      setUnavailable(false);
    } catch { setUnavailable(true); }
  }, [entityId, session?.access_token]);
  useEffect(() => { void load(); }, [load, plannerChangedAt]);
  if (unavailable) return <View style={styles.card}><AppText variant="bodySmall" tone="secondary">Esta tarea ya no está disponible</AppText></View>;
  if (!task) return <View style={styles.card}><AppText variant="bodySmall" tone="secondary">Cargando tarea…</AppText></View>;
  const assignee = task.assigned_member?.display_name ?? 'Sin asignar';
  const canClaim = claimAvailable && assignmentVersion !== null;
  const claim = async () => {
    if (!session?.access_token || assignmentVersion === null) return;
    setClaiming(true);
    try {
      await claimPlannerTaskV1(session.access_token, task.id, assignmentVersion);
    } catch {
      // The canonical reload below reflects an already-claimed or permission
      // result without pretending the local mutation succeeded.
    } finally {
      // Success and conflict both re-read Planner's canonical authority. In a
      // claim race this removes the stale CTA and shows the winner immediately.
      markPlannerChanged();
      await load();
      setClaiming(false);
    }
  };
  return <View testID="messages.taskCard" style={styles.card} accessibilityLabel={`Tarea: ${task.title}. ${assignee}. Estado ${task.status}`}>
    <View style={styles.icon}><HomePlusIcon name="checkbox-outline" size={19} color={colors.terracotta[600]} /></View>
    <View style={styles.copy}><AppText variant="caption" tone="tertiary" weight="800">TAREA</AppText><AppText variant="bodySmall" weight="800" numberOfLines={2}>{task.title}</AppText><AppText variant="caption" tone="secondary" numberOfLines={2}>{task.due_date ?? 'Sin fecha'} · {assignee} · {task.status === 'completed' ? 'Completada' : 'Pendiente'}</AppText></View>
    <View style={styles.actions}>{canClaim ? <Pressable testID="messages.taskCard.claim" onPress={() => void claim()} disabled={claiming} accessibilityRole="button" accessibilityLabel={`Me encargo de ${task.title}`} style={styles.action}><AppText variant="caption" weight="800">{claiming ? 'Actualizando…' : 'Me encargo'}</AppText></Pressable> : null}<Pressable testID="messages.taskCard.open" onPress={() => navigation.navigate('TaskDetailFromMessage', { entityId: task.id, source: 'messages', returnTo: 'previous' })} accessibilityRole="button" accessibilityLabel={`Ver tarea ${task.title}`} style={styles.action}><AppText variant="caption" weight="800">Ver tarea</AppText></Pressable></View>
  </View>;
}


function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({ card: { width: 274, minHeight: 104, padding: spacing[3], borderWidth: 1, borderColor: colors.border.default, borderRadius: radius.lg, backgroundColor: colors.surface.card }, icon: { width: 30, height: 30, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.terracotta[50] }, copy: { gap: 2, marginTop: spacing[1] }, actions: { flexDirection: 'row', marginTop: spacing[2], borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border.subtle }, action: { minHeight: 44, flex: 1, alignItems: 'center', justifyContent: 'center' } });
}
