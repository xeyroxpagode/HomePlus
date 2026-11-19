import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, StyleSheet, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { getInventoryAlerts, type InventoryAlerts } from '../../services/inventory';
import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import { fetchPlannerCapabilitiesCached } from '../../services/plannerCapabilities';
import { AppButton, AppCard, AppText, EmptyState, ErrorState, Skeleton, UndoToast } from '../../components/ui';
import { spacing } from '../../constants/theme';
import { HomePlusIcon, type HomePlusIconName } from '../../constants/icons';
import { useHomePlannerSummary } from '../../services/planner/useHomePlannerSummary';
import { type HomeSummaryTask } from '../../services/planner/homeSummaryTypes';
import { resolveOneTapEligibility } from '../../services/planner/homeTaskOneTapEligibility';
import {
  completeTaskFromHome,
  activeCompletionForTask,
  type CompletionOutcome,
} from '../../services/planner/homeTaskOneTapCompletion';
import { createPlannerVersionedMutationIntent } from '../../services/planner/plannerMutationIntent';
import type { PlannerCapabilitiesProjection } from '../../services/plannerCapabilities';
import { useHomeDailySignals } from '../../services/planner/useHomeDailySignals';
import { useAppRefresh } from '../../context/AppRefreshContext';
import { useAppTheme } from '../../context/AppThemeContext';

// ---------------------------------------------------------------------------
// Format helpers (kept from previous implementation; pure)
// ---------------------------------------------------------------------------

const formatDate = (value?: string | null) => {
  if (!value) return 'Sin fecha';
  const date = value.includes('T') ? new Date(value) : new Date(`${value}T00:00:00`);
  return date.toLocaleDateString('es-AR', { day: '2-digit', month: 'short' });
};

const formatTime = (value?: string | null) => {
  if (!value) return '';
  return new Date(value).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
};

const localDateKey = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;

const formatScheduleTime = (minutes: number) =>
  `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

const taskStatusLabel: Record<HomeSummaryTask['status'], string> = {
  pending: 'Pendiente',
  awaiting_verification: 'Por verificar',
};

const completionMessageForOutcome: Record<CompletionOutcome['kind'], string> = {
  success: 'Tarea completada.',
  conflict: 'La tarea fue modificada por otra persona. Refresca para ver el estado actual.',
  forbidden: 'No tienes permiso para completar esta tarea.',
  not_found: 'La tarea ya no existe.',
  validation: 'No se puede completar: estado inválido.',
  conflict_other: 'Hubo un conflicto. Refresca e intentalo de nuevo.',
  timeout: 'La conexión tardó demasiado. Intentalo nuevamente.',
  offline: 'Sin conexión. Intentalo más tarde.',
  server: 'Error del servidor. Intentalo más tarde.',
  abort: '',
  unknown_error: 'No pudimos completar la tarea.',
};

// ---------------------------------------------------------------------------
// Inventory urgency card (unchanged)
// ---------------------------------------------------------------------------

function HomeSectionHeader({
  title,
  actionLabel,
  onAction,
}: {
  title: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const styles = useThemeStyles(createStylesForTheme);

  const { colors } = useAppTheme();
  return (
    <View style={styles.sectionHeader}>
      <AppText variant="title3">{title}</AppText>
      {actionLabel && onAction ? (
        <TouchableOpacity
          style={styles.sectionAction}
          onPress={onAction}
          accessibilityRole="button"
          accessibilityLabel={actionLabel}
        >
          <AppText variant="caption" tone="brand" weight="700">{actionLabel}</AppText>
          <HomePlusIcon name="chevron-forward-outline" size={16} color={colors.brand} />
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

function HomeListRow({
  icon,
  title,
  detail,
  onPress,
  accessibilityLabel,
  tone = 'neutral',
  trailing,
  divider = false,
}: {
  icon: HomePlusIconName;
  title: string;
  detail?: string;
  onPress: () => void;
  accessibilityLabel?: string;
  tone?: 'neutral' | 'danger' | 'warning';
  trailing?: React.ReactNode;
  divider?: boolean;
}) {
  const styles = useThemeStyles(createStylesForTheme);

  const { colors } = useAppTheme();
  const iconColor = tone === 'danger' ? colors.danger.base : tone === 'warning' ? colors.warning.base : colors.terracotta[500];
  const iconSurface = tone === 'danger' ? colors.danger.soft : tone === 'warning' ? colors.warning.soft : colors.surface.soft;

  return (
    <TouchableOpacity
      style={[styles.listRow, divider ? { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border.subtle } : null]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? `${title}${detail ? `. ${detail}` : ''}`}
    >
      <View style={[styles.rowIcon, { backgroundColor: iconSurface }]}>
        <HomePlusIcon name={icon} size={20} color={iconColor} />
      </View>
      <View style={styles.rowCopy}>
        <AppText variant="bodySmall" weight="700" numberOfLines={2}>{title}</AppText>
        {detail ? <AppText variant="caption" tone={tone === 'danger' ? 'danger' : 'secondary'} numberOfLines={2}>{detail}</AppText> : null}
      </View>
      {trailing ?? <HomePlusIcon name="chevron-forward-outline" size={19} color={colors.text.tertiary} />}
    </TouchableOpacity>
  );
}

function InventoryUrgencyCard({
  alerts,
  onPress,
}: {
  alerts: InventoryAlerts | null;
  onPress: () => void;
}) {
  const styles = useThemeStyles(createStylesForTheme);

  if (!alerts) return null;

  const urgentCount = alerts.low_stock_count
    + alerts.out_of_stock_count
    + alerts.pending_restock_requests_count;

  if (urgentCount === 0) return null;

  const firstOut = alerts.out_of_stock_items[0];
  const firstLow = alerts.low_stock_items[0];

  const headline = firstOut
    ? `Sin stock: ${firstOut.name}`
    : firstLow
      ? `${firstLow.name} está por terminarse`
      : `${alerts.pending_restock_requests_count} reposición pendiente`;

  const summary = [
    alerts.out_of_stock_count > 0
      ? `${alerts.out_of_stock_count} sin stock`
      : null,
    alerts.low_stock_count > 0
      ? `${alerts.low_stock_count} con stock bajo`
      : null,
    alerts.pending_restock_requests_count > 0
      ? `${alerts.pending_restock_requests_count} ${alerts.pending_restock_requests_count === 1 ? 'reposición por aprobar' : 'reposiciones por aprobar'}`
      : null,
  ].filter(Boolean).join(' · ');

  return (
    <AppCard variant="warning" padding="compact" contentStyle={styles.compactCardContent} style={styles.attentionCard}>
      <HomeListRow icon="archive" title={headline} detail={summary} onPress={onPress} tone="warning" />
    </AppCard>
  );
}

function HomeConnectionError({ onRetry }: { onRetry: () => void }) {
  return (
    <ErrorState
      title="No pudimos actualizar la información"
      description="Revisá tu conexión e intentá nuevamente."
      retryLabel="Intentar de nuevo"
      onRetry={onRetry}
    />
  );
}

function HomeRefreshNotice({ onRetry }: { onRetry: () => void }) {
  const styles = useThemeStyles(createStylesForTheme);

  return (
    <AppCard variant="quiet" padding="compact" style={styles.refreshNotice}>
      <View style={styles.refreshNoticeContent}>
        <View style={styles.refreshNoticeCopy}>
          <AppText variant="bodySmall" weight="700">No pudimos actualizar la información</AppText>
          <AppText variant="caption" tone="secondary">Revisá tu conexión e intentá nuevamente.</AppText>
        </View>
        <AppButton title="Intentar de nuevo" variant="secondary" size="sm" onPress={onRetry} />
      </View>
    </AppCard>
  );
}

function useHomeInventoryAlerts(refreshSignal = 0) {
  const { session } = useAuth();
  const accessToken = session?.access_token;
  const [alerts, setAlerts] = useState<InventoryAlerts | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!accessToken) return;

    setLoading(true);
    try {
      const response = await getInventoryAlerts(accessToken);
      setAlerts(response.alerts);
    } catch {
      setAlerts(null);
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );

  // Inventory mutations notify Home as soon as their canonical response is
  // available. This avoids waiting for a tab focus or a periodic refresh.
  useEffect(() => {
    if (refreshSignal > 0) void refresh();
  }, [refresh, refreshSignal]);

  return { alerts, loading, refresh };
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function HomePlannerSections() {
  const styles = useThemeStyles(createStylesForTheme);

  const { colors } = useAppTheme();
  const navigation = useNavigation<any>();
  const { session, authMe } = useAuth();
  const { currentHousehold, members } = useHousehold();
  const { markPlannerChanged, homeChangedAt } = useAppRefresh();
  const { state, refresh } = useHomePlannerSummary();
  const { alerts: inventoryAlerts } = useHomeInventoryAlerts(homeChangedAt);
  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? null;

  // Capability projection for one-tap eligibility (cached; fresh on switch).
  const [capabilities, setCapabilities] = useState<PlannerCapabilitiesProjection | null>(null);
  const [completionVisualTask, setCompletionVisualTask] = useState<HomeSummaryTask | null>(null);
  const [completionFeedback, setCompletionFeedback] = useState<{ message: string; tone: 'success' | 'error' } | null>(null);
  const completionVisualTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const confirmedCompletionTaskId = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (completionVisualTimer.current) clearTimeout(completionVisualTimer.current);
    };
  }, []);

  useEffect(() => {
    if (completionVisualTimer.current) clearTimeout(completionVisualTimer.current);
    completionVisualTimer.current = null;
    confirmedCompletionTaskId.current = null;
    setCompletionVisualTask(null);
    setCompletionFeedback(null);
  }, [householdId]);
  useEffect(() => {
    if (!accessToken || !householdId || !authMe) return;
    let cancelled = false;
    fetchPlannerCapabilitiesCached(accessToken, {
      accountId: authMe.person?.auth_user_id ?? '',
      householdId,
      membershipId: authMe.memberships.find(m => m.household_id === householdId && m.status === 'active')?.id ?? '',
    }).then((caps) => {
      if (!cancelled) setCapabilities(caps);
    }).catch(() => {
      if (!cancelled) setCapabilities(null);
    });
    return () => { cancelled = true; };
  }, [accessToken, householdId, authMe]);

  const myMembershipId = useMemo(() => {
    return authMe?.memberships.find(
      (membership) => membership.household_id === householdId && membership.status === 'active',
    )?.id ?? '';
  }, [authMe?.memberships, householdId]);

  const memberNameById = useMemo(() => {
    const map = new Map<string, string>();
    members.forEach((member) => map.set(member.id, member.user?.nombre || 'Miembro'));
    return map;
  }, [members]);

  const schedulePeople = useMemo(() => {
    const people = new Map<string, { id: string; name: string }>();
    if (authMe?.person?.id) people.set(authMe.person.id, { id: authMe.person.id, name: 'Vos' });
    members.forEach((member) => {
      if (!member.user_id) return;
      people.set(member.user_id, { id: member.user_id, name: member.user?.nombre || 'Integrante' });
    });
    return [...people.values()];
  }, [authMe, members]);

  const daily = useHomeDailySignals({ accessToken, householdId, people: schedulePeople });

  const openPlanner = useCallback((initialTab: 'tasks' | 'calendar' | 'plans') => {
    navigation.navigate('PlannerTab', {
      screen: 'PlannerHome',
      params: { initialTab, refreshKey: Date.now() },
    });
  }, [navigation]);

  const { summary, partialErrors, status } = state;
  const hasSummary = summary !== null;
  const hasDailyError = Boolean(daily.attentionError || daily.schedulesError || daily.activityError);
  const hasPartial = partialErrors.length > 0;
  const canConfirmPlannerEmpty = Boolean(summary) && !hasPartial && (status === 'ready' || status === 'empty');
  const today = localDateKey(new Date());
  const todayTasks = useMemo(
    () => summary?.tasks.filter((task) => task.due_date === today) ?? [],
    [summary, today],
  );
  const visibleTodayTasks = useMemo(() => {
    if (!completionVisualTask || todayTasks.some((task) => task.id === completionVisualTask.id)) return todayTasks;
    return [...todayTasks, completionVisualTask];
  }, [completionVisualTask, todayTasks]);

  useEffect(() => {
    if (!completionVisualTask || confirmedCompletionTaskId.current !== completionVisualTask.id) return;

    const sourceTask = todayTasks.find((task) => task.id === completionVisualTask.id);
    const sourceConfirmedChange = !sourceTask
      || sourceTask.version !== completionVisualTask.version
      || sourceTask.status !== completionVisualTask.status;
    if (!sourceConfirmedChange || completionVisualTimer.current) return;

    completionVisualTimer.current = setTimeout(() => {
      setCompletionVisualTask((current) => current?.id === completionVisualTask.id ? null : current);
      confirmedCompletionTaskId.current = null;
      completionVisualTimer.current = null;
    }, 420);
  }, [completionVisualTask, todayTasks]);
  const todayEvents = summary?.events.filter((event) => localDateKey(new Date(event.starts_at)) === today) ?? [];
  const todaySchedules = daily.schedules.filter((schedule) => schedule.days_of_week.includes(new Date().getDay()));
  const upcomingTasks = summary?.tasks.filter((task) => task.due_date !== today && task.due_date && task.due_date > today) ?? [];
  const upcomingEvents = summary?.events.filter((event) => localDateKey(new Date(event.starts_at)) !== today) ?? [];
  const plannerLoading = status === 'initial_loading' || status === 'refreshing';
  const todayEmpty = !plannerLoading && !daily.loading && canConfirmPlannerEmpty
    && !daily.schedulesError && visibleTodayTasks.length + todayEvents.length + todaySchedules.length === 0;
  const upcomingEmpty = !plannerLoading && canConfirmPlannerEmpty
    && upcomingEvents.length + upcomingTasks.length === 0;
  const activityEmpty = !daily.loading && !daily.activityError && daily.activity.length === 0;
  const refreshAll = useCallback(async () => {
    await Promise.all([refresh(), daily.refresh()]);
  }, [daily, refresh]);

  // -------------------------------------------------------------------------
  // One-tap completion handler
  // -------------------------------------------------------------------------
  const handleCompleteTask = useCallback(async (task: HomeSummaryTask) => {
    if (!accessToken || !householdId || !myMembershipId || completionVisualTask) return;

    // Re-check eligibility at tap time (capability might have changed).
    const eligibility = resolveOneTapEligibility({
      projection: capabilities,
      actorMembershipId: myMembershipId,
      task,
      hasPendingMutation: false,
    });
    if (!eligibility.eligible) {
      return;
    }

    setCompletionVisualTask(task);

    // Build intent and completion options.
    const intent = createPlannerVersionedMutationIntent({
      kind: 'versioned',
      entityKind: 'planner.tasks',
      entityVersion: task.version,
    });

    const result = await completeTaskFromHome({
      accessToken,
      scope: { householdId },
      taskId: task.id,
      version: task.version,
      existingIntent: intent,
    });

    if (result.ok) {
      // Announce completion for screen readers.
      AccessibilityInfo.announceForAccessibility(completionMessageForOutcome[result.outcome.kind] || 'Tarea completada.');
      confirmedCompletionTaskId.current = task.id;
      setCompletionFeedback({ message: 'Tarea completada', tone: 'success' });
      markPlannerChanged();
      // The cache invalidation is handled inside completeTaskFromHome;
      // the hook's plannerChangedAt will fire and re-fetch Summary.
    } else {
      // Error: show accessible toast / inline message.
      const msg = completionMessageForOutcome[result.outcome.kind] || 'No pudimos completar la tarea.';
      AccessibilityInfo.announceForAccessibility(msg);
      confirmedCompletionTaskId.current = null;
      setCompletionVisualTask((current) => current?.id === task.id ? null : current);
      if (msg) setCompletionFeedback({ message: msg, tone: 'error' });
    }
  }, [accessToken, householdId, myMembershipId, capabilities, completionVisualTask, markPlannerChanged]);

  // -------------------------------------------------------------------------
  // Render sections
  // -------------------------------------------------------------------------

  return <View style={styles.container}>
    {status === 'forbidden' ? <ErrorState title="Sin permiso" description={state.errorCode === 'planner_forbidden' ? "No tenés permiso para ver el Organizador de este hogar." : 'No tenés permiso para ver la información de este hogar.'} style={styles.stateCard} onRetry={refreshAll} /> : null}
    {!hasSummary && (status === 'recoverable_error' || status === 'offline_empty') ? <View style={styles.stateCard}><HomeConnectionError onRetry={refreshAll} /></View> : null}
    {hasSummary && (status === 'offline_stale' || hasDailyError) ? <HomeRefreshNotice onRetry={refreshAll} /> : null}

    {(!daily.attentionError && daily.attention.length > 0) || Boolean(inventoryAlerts && (inventoryAlerts.low_stock_count + inventoryAlerts.out_of_stock_count + inventoryAlerts.pending_restock_requests_count > 0)) ? (
      <View style={styles.section}>
        <HomeSectionHeader
          title="Necesita atención"
        />
        <View style={styles.attentionStack}>
          {daily.attention.map((item) => (
            <AppCard key={item.attentionId} variant="danger" padding="compact" style={styles.attentionCard}>
              <HomeListRow
                icon="alert-circle"
                title={item.title}
                detail={item.summary}
                tone="danger"
                onPress={() => navigation.navigate('PlannerTab', { screen: 'PlannerAttentionActivity', params: { source: 'home', returnTo: 'home' } })}
              />
            </AppCard>
          ))}
          <InventoryUrgencyCard alerts={inventoryAlerts} onPress={() => navigation.navigate('MoreTab', { screen: 'Inventory' })} />
        </View>
      </View>
    ) : null}

    <View style={styles.section}>
      <HomeSectionHeader title="Hoy" />
      {todayEmpty ? <EmptyState variant="compact" title="Sin actividades para hoy" /> : <AppCard variant="default" padding="compact" contentStyle={styles.compactCardContent} style={styles.listCard}>
      {status === 'initial_loading' || status === 'refreshing' || daily.loading ? <Skeleton variant="paragraph" lines={3} style={styles.skeletonBlock} /> : <>
        {visibleTodayTasks.map((task, index) => { const assignedName = task.assigned_to_member_id ? memberNameById.get(task.assigned_to_member_id) ?? 'Miembro' : 'Sin asignar'; const lock = activeCompletionForTask(task.id); const showingCompletion = completionVisualTask?.id === task.id; const showComplete = showingCompletion || resolveOneTapEligibility({ projection: capabilities, actorMembershipId: myMembershipId, task, hasPendingMutation: !!lock }).eligible; return <HomeListRow key={task.id} divider={index > 0} icon={showingCompletion ? 'checkmark-circle' : 'ellipse-outline'} title={task.title} detail={showingCompletion ? 'Tarea completada' : `${taskStatusLabel[task.status]} · ${assignedName}`} onPress={() => openPlanner('tasks')} accessibilityLabel={`Tarea ${task.title}, ${showingCompletion ? 'completada' : taskStatusLabel[task.status]}, asignada a ${assignedName}`} trailing={showComplete ? <TouchableOpacity onPress={() => void handleCompleteTask(task)} disabled={Boolean(completionVisualTask) || !!lock} accessibilityRole="button" accessibilityLabel={showingCompletion ? `${task.title} completada` : `Completar ${task.title}`} accessibilityState={{ busy: Boolean(completionVisualTask) || !!lock, checked: showingCompletion }} style={styles.completeButton}><HomePlusIcon name={showingCompletion ? 'checkmark-circle' : lock ? 'refresh-outline' : 'ellipse-outline'} color={showingCompletion ? colors.success.base : lock ? colors.text.tertiary : colors.text.secondary} size={22} /></TouchableOpacity> : undefined} />; })}
        {todayEvents.map((event, index) => <HomeListRow key={event.id} divider={visibleTodayTasks.length + index > 0} icon="today-outline" title={event.title} detail={`Evento · ${event.all_day ? 'Todo el día' : formatTime(event.starts_at)}`} onPress={() => openPlanner('calendar')} accessibilityLabel={`Evento de hoy: ${event.title}`} />)}
        {daily.schedulesError ? <AppText variant="bodySmall" tone="secondary" style={styles.emptyInline}>No se pudieron actualizar los horarios.</AppText> : todaySchedules.map((schedule, index) => <HomeListRow key={schedule.id} divider={visibleTodayTasks.length + todayEvents.length + index > 0} icon="calendar-outline" title={schedule.title} detail={`${schedule.personName} · ${formatScheduleTime(schedule.start_minutes)}–${formatScheduleTime(schedule.end_minutes)}`} onPress={() => openPlanner('plans')} accessibilityLabel={`Horario de ${schedule.personName}: ${schedule.title}, ${formatScheduleTime(schedule.start_minutes)} a ${formatScheduleTime(schedule.end_minutes)}`} />)}

      </>}
      </AppCard>}
    </View>

    <View style={styles.section}>
      <HomeSectionHeader title="Próximamente" actionLabel="Ver calendario" onAction={() => openPlanner('calendar')} />
      {upcomingEmpty ? <EmptyState variant="compact" title="Sin actividades próximas" /> : <AppCard variant="default" padding="compact" contentStyle={styles.compactCardContent} style={styles.listCard}>
        {status === 'initial_loading' || status === 'refreshing' ? <Skeleton variant="paragraph" lines={2} style={styles.skeletonBlock} /> : <>{upcomingEvents.map((event, index) => <HomeListRow key={event.id} divider={index > 0} icon="today-outline" title={event.title} detail={`${formatDate(event.starts_at)} ${event.all_day ? 'Todo el día' : formatTime(event.starts_at)}`} onPress={() => openPlanner('calendar')} />)}{upcomingTasks.map((task, index) => <HomeListRow key={task.id} divider={upcomingEvents.length + index > 0} icon="ellipse-outline" title={task.title} detail={`Tarea · ${formatDate(task.due_date)}`} onPress={() => openPlanner('tasks')} />)}</>}
      </AppCard>}
    </View>

    <View style={styles.section}>
      <HomeSectionHeader title="Qué cambió" actionLabel="Ver actividad" onAction={() => navigation.navigate('PlannerTab', { screen: 'PlannerAttentionActivity', params: { source: 'home', returnTo: 'home' } })} />
      {activityEmpty ? <EmptyState variant="compact" title="Sin novedades recientes" /> : <AppCard variant="default" padding="compact" contentStyle={styles.compactCardContent} style={styles.listCard}>
        {daily.loading ? <Skeleton variant="paragraph" lines={2} style={styles.skeletonBlock} /> : daily.activityError ? <AppText variant="bodySmall" tone="secondary" style={styles.emptyInline}>No se pudo actualizar la actividad.</AppText> : daily.activity.length > 0 ? daily.activity.map((item, index) => <HomeListRow key={item.activityId} divider={index > 0} icon="time-outline" title={item.summary} detail={new Date(item.timestamp).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })} onPress={() => navigation.navigate('PlannerTab', { screen: 'PlannerAttentionActivity', params: { source: 'home', returnTo: 'home' } })} />) : null}
      </AppCard>}
    </View>

    {hasPartial ? <ErrorState title="Algunos datos no están disponibles" description="No mostramos información incompleta. Podés reintentar la carga." onRetry={refreshAll} /> : null}
    <UndoToast
      visible={Boolean(completionFeedback)}
      message={completionFeedback?.message ?? ''}
      tone={completionFeedback?.tone ?? 'success'}
      duration={2000}
      onDismiss={() => setCompletionFeedback(null)}
    />
  </View>;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  container: { gap: spacing[5] },
  section: { gap: spacing[2] },
  attentionStack: { gap: spacing[2] },
  attentionCard: { marginBottom: 0 },
  listCard: { marginBottom: 0 },
  compactCardContent: {
    paddingVertical: spacing[1],
    paddingHorizontal: spacing[3],
  },
  stateCard: { marginBottom: spacing[1] },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 32,
  },
  sectionAction: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
    paddingLeft: spacing[2],
  },
  listRow: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
    paddingVertical: spacing[1],
  },
  listRowDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border.subtle,
  },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowCopy: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  completeButton: {
    padding: spacing[1],
    minWidth: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyInline: {
    minHeight: 44,
    justifyContent: 'center',
    paddingTop: spacing[2],
  },
  skeletonBlock: { paddingVertical: spacing[2] },
  partialErrorCard: {
    marginTop: spacing[2],
    borderLeftWidth: 3,
    borderLeftColor: colors.warning.base,
  },
  refreshNotice: {
    marginBottom: spacing[1],
  },
  refreshNoticeContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
  refreshNoticeCopy: {
    flex: 1,
    gap: spacing[1],
  },
});
}
