import React, { useCallback } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import { AppText } from '../ui/AppText';
import { InteractivePressable } from '../ui/InteractivePressable';
import { Skeleton } from '../ui/Skeleton';
import { StatusBadge } from '../ui/StatusBadge';
import { HomePlusIcon } from '../../constants/icons';
import { colors, radius, spacing, touchTargets } from '../../constants/theme';
import { ErrorBar } from './ErrorBar';
import { useAssetPlannerItems } from '../../hooks/assets/useAssetPlannerItems';
import type { AssetPlannerItemDto } from '../../services/assets/plannerItems';

/**
 * HOMePLUS Assets — S7-07: sección "PRÓXIMO" del detalle del activo.
 *
 * Muestra las Tasks y los Events de Planner que referencian el activo. El
 * read model es de Assets; las entidades son de Planner: al tocar un item se
 * abre el detalle REAL de Planner y al volver la sección se revalida.
 *
 * Copy congelado (S7):
 *   - Sección: PRÓXIMO
 *   - Vacío: "Todavía no programaste nada para este activo."
 *   - CTA: "Programar algo"
 *   - Badge de vencida: "Vencida"
 *   - "Ver todos (N)" y "Mostrando 20 de N"
 */

const formatDate = (value: string | null): string => {
  if (!value) return '';
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return value;
  return `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`;
};

const formatTime = (value: string | null): string => (value ? value.slice(0, 5) : '');

const pad2 = (value: number): string => String(value).padStart(2, '0');

/**
 * Los Eventos llegan con `effective_date`/`effective_time` derivados del
 * instante en UTC: mostrarlos crudo corre la hora (y a veces el día) en
 * Paraguay. Para eventos se usa `effective_at` y se formatea en la zona local
 * del dispositivo. Las Tasks conservan fecha y hora civiles (`due_date` /
 * `due_time`), que ya son "en casa".
 */
const localParts = (iso: string): { date: string; time: string } | null => {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return {
    date: `${pad2(parsed.getDate())}/${pad2(parsed.getMonth() + 1)}`,
    time: `${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}`,
  };
};

const todayParts = (): { date: string; year: number } => {
  const now = new Date();
  return { date: `${pad2(now.getDate())}/${pad2(now.getMonth() + 1)}`, year: now.getFullYear() };
};

const tomorrowParts = (): string => {
  const now = new Date();
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  return `${pad2(tomorrow.getDate())}/${pad2(tomorrow.getMonth() + 1)}`;
};

/** "Hoy" / "Mañana" cuando aplica; dd/mm con año sólo si no es el año actual. */
const relativeDateLabel = (date: string, year: number | null): string => {
  const today = todayParts();
  if (date === today.date) return 'Hoy';
  if (date === tomorrowParts()) return 'Mañana';
  if (year !== null && year !== today.year) return `${date}/${year}`;
  return date;
};

const whenLabel = (item: AssetPlannerItemDto): string => {
  if (item.kind === 'event' && item.effective_at) {
    const local = localParts(item.effective_at);
    if (local) {
      const day = relativeDateLabel(local.date, new Date(item.effective_at).getFullYear());
      return local.time ? `${day} · ${local.time}` : day;
    }
  }
  const date = formatDate(item.effective_date);
  const time = formatTime(item.effective_time);
  if (date && time) {
    const year = item.effective_date ? Number(item.effective_date.slice(0, 4)) : null;
    return `${relativeDateLabel(date, Number.isNaN(year as number) ? null : year)} · ${time}`;
  }
  if (date) {
    const year = item.effective_date ? Number(item.effective_date.slice(0, 4)) : null;
    return relativeDateLabel(date, Number.isNaN(year as number) ? null : year);
  }
  return 'Sin fecha';
};

export type AssetPlannerItemsSectionProps = {
  accessToken: string | null;
  householdId: string | null;
  assetId: string;
  /** Puede el usuario abrir el composer de Planner desde acá. */
  canCreateAny: boolean;
  onCreateTask: () => void;
  onCreateEvent: () => void;
};

export function AssetPlannerItemsSection({
  accessToken,
  householdId,
  assetId,
  canCreateAny,
  onCreateTask,
  onCreateEvent,
}: AssetPlannerItemsSectionProps) {
  const navigation = useNavigation<any>();
  const plannerItems = useAssetPlannerItems(accessToken, householdId, assetId);

  const openInPlanner = useCallback(
    (item: AssetPlannerItemDto) => {
      navigation.navigate('PlannerTab', {
        screen: item.kind === 'event' ? 'EventDetail' : 'TaskDetail',
        params: {
          entityId: item.id,
          source: 'assets',
          returnTo: 'previous',
        },
      });
    },
    [navigation],
  );

  const hasItems = plannerItems.items.length > 0;
  // Sólo tiene sentido ofrecer "Ver todos" si todavía no se expandió: una vez
  // expandido el botón quedaría sin efecto.
  const canShowAll = !plannerItems.showAll && plannerItems.total > plannerItems.items.length;
  const truncated = plannerItems.total > plannerItems.items.length
    && plannerItems.items.length >= 20;

  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <AppText variant="caption" weight="700" tone="secondary" accessibilityRole="header">
          PRÓXIMO
        </AppText>
        {canShowAll ? (
          <Pressable
            onPress={() => plannerItems.setShowAll(true)}
            accessibilityRole="button"
            accessibilityLabel={`Ver todos los items programados (${plannerItems.total})`}
            accessibilityHint="Muestra los 20 items programados más próximos"
            hitSlop={INLINE_LINK_HIT_SLOP}
            style={styles.headerAction}
          >
            <AppText variant="caption" weight="600" tone="brand">
              Ver todos ({plannerItems.total})
            </AppText>
          </Pressable>
        ) : null}
      </View>

      {plannerItems.error ? (
        <ErrorBar
          visible
          message={plannerItems.error}
          action={{ label: 'Reintentar', onPress: plannerItems.reload }}
        />
      ) : null}

      {plannerItems.loading && !hasItems ? (
        <View style={styles.skeletons}>
          <Skeleton style={styles.skeleton} />
          <Skeleton style={styles.skeleton} />
        </View>
      ) : hasItems ? (
        <View style={styles.card}>
          {plannerItems.items.map((item, index) => {
            const kindLabel = item.kind === 'event' ? 'Evento' : 'Tarea';
            const when = whenLabel(item);
            return (
              <InteractivePressable
                key={item.id}
                onPress={() => openInPlanner(item)}
                accessibilityRole="button"
                accessibilityLabel={`${kindLabel}: ${item.title}. ${when}${item.overdue ? '. Vencida' : ''}`}
                accessibilityHint="Abre el detalle en Planner"
                pressScale={0.99}
                pressedOpacity={0.85}
              >
                <View style={styles.row}>
                  {index > 0 ? <View style={styles.divider} /> : null}
                  <View style={styles.rowContent}>
                    <View style={styles.titleRow}>
                      <View accessible={false} importantForAccessibility="no">
                        <HomePlusIcon
                          name={item.kind === 'event' ? 'calendar-outline' : 'checkmark-circle-outline'}
                          size={16}
                          color={colors.text.tertiary}
                        />
                      </View>
                      <AppText variant="bodySmall" weight="600" numberOfLines={2} style={styles.itemTitle}>
                        {item.title}
                      </AppText>
                      {item.overdue ? (
                        <StatusBadge label="Vencida" tone="warning" />
                      ) : null}
                    </View>
                    <AppText variant="caption" tone="tertiary">
                      {kindLabel} · {when}
                    </AppText>
                  </View>
                  <View accessible={false} importantForAccessibility="no">
                    <HomePlusIcon
                      name="chevron-forward-outline"
                      size={16}
                      color={colors.text.tertiary}
                    />
                  </View>
                </View>
              </InteractivePressable>
            );
          })}
          {truncated ? (
            <AppText variant="caption" tone="tertiary" style={styles.footerNote}>
              Mostrando 20 de {plannerItems.total}
            </AppText>
          ) : null}
        </View>
      ) : (
        <View style={styles.empty}>
          {canCreateAny ? (
            <Pressable
              onPress={onCreateTask}
              accessibilityRole="button"
              accessibilityLabel="Todavía no programaste nada para este activo. Programar algo"
              accessibilityHint="Abre el composer de Planner"
              style={styles.emptyInner}
            >
              <View accessible={false} importantForAccessibility="no">
                <HomePlusIcon name="calendar-outline" size={20} color={colors.text.tertiary} />
              </View>
              <AppText variant="bodySmall" tone="secondary">
                Todavía no programaste nada para este activo.
              </AppText>
              <AppText variant="caption" weight="600" tone="brand">
                Programar algo
              </AppText>
            </Pressable>
          ) : (
            <View style={styles.emptyInner}>
              <AppText variant="bodySmall" tone="secondary">
                Todavía no programaste nada para este activo.
              </AppText>
            </View>
          )}
        </View>
      )}

      {hasItems && canCreateAny ? (
        <Pressable
          onPress={onCreateTask}
          accessibilityRole="button"
          accessibilityLabel="Programar algo para este activo"
          accessibilityHint="Abre el composer de Planner"
          style={styles.footer}
        >
          <AppText variant="caption" weight="600" tone="brand">
            Programar algo
          </AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

/** Diana táctil mínima para links de texto inline sin alterar el layout. */
const INLINE_LINK_HIT_SLOP = { top: 14, bottom: 14, left: 8, right: 8 };

const styles = StyleSheet.create({
  section: { gap: spacing[2] },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing[2],
  },
  headerAction: {
    minHeight: touchTargets.normal,
    justifyContent: 'center',
  },
  skeletons: { gap: spacing[2] },
  skeleton: { height: 72, borderRadius: radius.lg },
  card: {
    backgroundColor: colors.surface.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
    paddingVertical: spacing[3],
    paddingHorizontal: spacing[4],
  },
  rowContent: {
    flex: 1,
    minWidth: 0,
    gap: spacing[1],
  },
  divider: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: colors.border.subtle,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
    minWidth: 0,
  },
  itemTitle: {
    flexShrink: 1,
  },
  empty: { paddingVertical: spacing[1] },
  emptyInner: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing[2],
    paddingVertical: spacing[3],
  },
  footer: {
    minHeight: touchTargets.normal,
    paddingVertical: spacing[3],
    paddingHorizontal: spacing[3],
    alignItems: 'center',
    justifyContent: 'center',
  },
  footerNote: {
    paddingBottom: spacing[3],
    paddingHorizontal: spacing[4],
    textAlign: 'center',
  },
});
