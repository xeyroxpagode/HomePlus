import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useAppTheme } from '../../context/AppThemeContext';
import type { LifecycleHistoryEpisode } from '../../services/assets';
import { AppText } from '../ui/AppText';
import { AppButton } from '../ui/AppButton';
import { InteractivePressable } from '../ui/InteractivePressable';
import { radius, spacing, touchTargets } from '../../constants/theme';
import { AssetFormSheet } from './AssetSheet';
import { ErrorBar } from './ErrorBar';
import { describeDisposition } from './assetLabels';

const ACTION_LABEL: Record<LifecycleHistoryEpisode['action'], string> = {
  ARCHIVED: 'Archivado',
  UNARCHIVED: 'Desarchivado',
  TRASHED: 'Papelera',
  RESTORED: 'Restaurado',
};

const ACTION_TONE: Record<LifecycleHistoryEpisode['action'], 'neutral' | 'warning' | 'danger' | 'success'> = {
  ARCHIVED: 'warning',
  UNARCHIVED: 'success',
  TRASHED: 'danger',
  RESTORED: 'success',
};

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const year = d.getFullYear();
  const hours = String(d.getHours()).padStart(2, '0');
  const mins = String(d.getMinutes()).padStart(2, '0');
  return `${day}/${month}/${year} ${hours}:${mins}`;
}

function describeContext(episode: LifecycleHistoryEpisode): string | null {
  if (!episode.last_context) return null;
  const parts: string[] = [];
  const { responsible, holder, placement } = episode.last_context;
  if (responsible?.display_name) parts.push(`Responsable: ${responsible.display_name}`);
  if (holder?.type === 'member' && holder.display_name) parts.push(`Lo tenía ${holder.display_name}`);
  else if (holder?.type === 'external' && holder.external_label) parts.push(`Lo tenía ${holder.external_label}`);
  if (placement?.type === 'property') parts.push(`Estaba en ${placement.property_name ?? 'una propiedad'}`);
  else if (placement?.type === 'external' && placement.external_text) parts.push(`Estaba en ${placement.external_text}`);
  return parts.length > 0 ? parts.join(' · ') : null;
}

// ── Minimum Detail Experience ─────────────────────────────────────────────────

export type AssetLifecycleHistorySectionProps = {
  episode: LifecycleHistoryEpisode;
  onViewFullHistory: () => void;
};

export function AssetLifecycleHistorySection({
  episode,
  onViewFullHistory,
}: AssetLifecycleHistorySectionProps) {
  const theme = useAppTheme();
  const tone = ACTION_TONE[episode.action];
  const contextLine = describeContext(episode);

  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <AppText variant="caption" weight="700" tone="secondary" accessibilityRole="header">
          HISTORIAL DE CICLO DE VIDA
        </AppText>
        <InteractivePressable
          onPress={onViewFullHistory}
          accessibilityRole="button"
          accessibilityLabel="Ver historial completo"
          accessibilityHint="Abre el historial completo de archivados y restauraciones"
          haptic="none"
          pressScale={0.99}
          style={styles.viewAllBtn}
        >
          <AppText variant="caption" weight="600" tone="brand">
            Ver historial completo
          </AppText>
        </InteractivePressable>
      </View>
      <View style={[styles.card, { borderColor: theme.colors.border.subtle }]}>
        <View style={styles.cardTop}>
          <View
            style={[
              styles.actionBadge,
              {
                backgroundColor:
                  tone === 'warning'
                    ? theme.colors.warning.soft
                    : tone === 'danger'
                      ? theme.colors.danger.soft
                      : theme.colors.success.soft,
              },
            ]}
          >
            <AppText variant="caption" weight="700" tone={tone === 'neutral' ? 'secondary' : tone}>
              {ACTION_LABEL[episode.action]}
            </AppText>
          </View>
          <AppText variant="caption" tone="tertiary">
            {formatTimestamp(episode.timestamp)}
          </AppText>
        </View>
        {describeDisposition(episode.disposition) ? (
          <AppText variant="bodySmall" weight="600">
            Motivo: {describeDisposition(episode.disposition)}
          </AppText>
        ) : null}
        {episode.note ? (
          <AppText variant="bodySmall" tone="secondary">
            {episode.note}
          </AppText>
        ) : null}
        {contextLine ? (
          <AppText variant="caption" tone="tertiary">
            {contextLine}
          </AppText>
        ) : null}
      </View>
    </View>
  );
}

// ── Full History Sheet ────────────────────────────────────────────────────────

export type AssetLifecycleHistorySheetProps = {
  visible: boolean;
  episodes: LifecycleHistoryEpisode[];
  loading: boolean;
  error?: string | null;
  onClose: () => void;
  onRetry?: () => void;
};

export function AssetLifecycleHistorySheet({
  visible,
  episodes,
  loading,
  error = null,
  onClose,
  onRetry,
}: AssetLifecycleHistorySheetProps) {
  return (
    <AssetFormSheet
      visible={visible}
      title="Historial de ciclo de vida"
      subtitle="Archivados, papelera y restauraciones"
      onRequestClose={onClose}
      footer={
        <AppButton
          variant="secondary"
          title="Cerrar"
          onPress={onClose}
          accessibilityLabel="Cerrar el historial"
        />
      }
    >
      <ScrollView
        style={styles.sheetScroll}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
      >
        {error ? (
          <ErrorBar
            visible
            message={error}
            action={onRetry ? { label: 'Reintentar', onPress: onRetry } : undefined}
          />
        ) : null}
        {loading ? (
          <AppText variant="bodySmall" tone="tertiary" style={styles.loadingText}>
            Cargando historial…
          </AppText>
        ) : episodes.length === 0 && !error ? (
          <AppText variant="bodySmall" tone="secondary" style={styles.emptyText}>
            Este activo todavía no tiene historial de ciclo de vida.
          </AppText>
        ) : (
          episodes.map((ep) => <HistoryRow key={ep.id} episode={ep} />)
        )}
      </ScrollView>
    </AssetFormSheet>
  );
}

function HistoryRow({ episode }: { episode: LifecycleHistoryEpisode }) {
  const theme = useAppTheme();
  const tone = ACTION_TONE[episode.action];
  const contextLine = describeContext(episode);

  return (
    <View style={[styles.row, { borderColor: theme.colors.border.subtle }]}>
      <View style={styles.rowTop}>
        <View
          style={[
            styles.actionBadgeSmall,
            {
              backgroundColor:
                tone === 'warning'
                  ? theme.colors.warning.soft
                  : tone === 'danger'
                    ? theme.colors.danger.soft
                    : theme.colors.success.soft,
            },
          ]}
        >
          <AppText variant="caption" weight="700" tone={tone === 'neutral' ? 'secondary' : tone}>
            {ACTION_LABEL[episode.action]}
          </AppText>
        </View>
        <AppText variant="caption" tone="tertiary">
          {formatTimestamp(episode.timestamp)}
        </AppText>
      </View>
      {describeDisposition(episode.disposition) ? (
        <AppText variant="bodySmall" weight="600">
          {describeDisposition(episode.disposition)}
        </AppText>
      ) : null}
      {episode.note ? (
        <AppText variant="bodySmall" tone="secondary">
          {episode.note}
        </AppText>
      ) : null}
      {contextLine ? (
        <AppText variant="caption" tone="tertiary">
          {contextLine}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing[2] },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing[2],
  },
  viewAllBtn: {
    minHeight: touchTargets.normal,
    paddingHorizontal: spacing[2],
    justifyContent: 'center',
  },
  card: {
    padding: spacing[4],
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing[2],
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing[2],
  },
  actionBadge: {
    paddingHorizontal: spacing[2],
    paddingVertical: spacing[1],
    borderRadius: radius.sm,
  },
  sheetScroll: {
    flexGrow: 0,
  },
  loadingText: { paddingVertical: spacing[4], textAlign: 'center' },
  emptyText: { paddingVertical: spacing[6], textAlign: 'center' },
  listContent: { gap: spacing[3], paddingBottom: spacing[4] },
  row: {
    padding: spacing[3],
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing[2],
  },
  rowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing[2],
  },
  actionBadgeSmall: {
    paddingHorizontal: spacing[2],
    paddingVertical: spacing[1],
    borderRadius: radius.sm,
  },
});
