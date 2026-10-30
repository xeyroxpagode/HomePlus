/**
 * HOMePLUS Assets — S8: one attached File row (shared by Asset/Record/Care).
 *
 * The row shows the LIVE HomeCloud metadata projected by the backend. It never
 * shows a cached copy of the File: the Assets relation stores only the
 * relation, and every read asks HomeCloud for the current truth.
 *
 * Lifecycle (frozen):
 *   available -> normal row, the viewer can be opened.
 *   trashed   -> badge "En la papelera", NO viewer.
 *   purging   -> badge "Se está eliminando", NO viewer.
 *   missing   -> "Archivo no disponible", NO metadata, NO viewer. The relation
 *                survives as a tombstone: nothing is auto-unlinked.
 */

import React from 'react';
import { StyleSheet, View } from 'react-native';

import { HomePlusIcon } from '../../constants/icons';
import { useAppTheme } from '../../context/AppThemeContext';
import { AppText } from '../ui/AppText';
import { InteractivePressable } from '../ui/InteractivePressable';
import { colors, iconSizes, spacing, touchTargets } from '../../constants/theme';
import type { AssetFileRelation, AssetFileState } from '../../services/assets/assetsFiles';

/** The frozen badges of the Assets file lifecycle. */
export const ASSET_FILE_STATE_BADGE: Record<
  AssetFileState,
  { readonly label: string; readonly tone: 'secondary' | 'warning' | 'danger' } | null
> = {
  available: null,
  trashed: { label: 'En la papelera', tone: 'warning' },
  purging: { label: 'Se está eliminando', tone: 'danger' },
  missing: null,
};

/** The frozen copy of a File that no longer exists. */
export const ASSET_FILE_MISSING_LABEL = 'Archivo no disponible';

/**
 * S9 — the label of the OWNER of a relation, for the aggregated list.
 *
 * It says where the File comes from. It NEVER implies that the ownership
 * changed: a Record file stays owned by its Record.
 */
export function assetFileOwnerLabel(relation: AssetFileRelation): string {
  if (relation.owner_type === 'asset') return 'Activo';
  if (relation.owner_type === 'record') return 'Registro';
  return 'Historial/Cuidado';
}

/**
 * S9 — the human label of the owner (its title or description).
 */
export function assetFileOwnerDetail(relation: AssetFileRelation): string | null {
  const context = relation.owner_context;
  if (!context) return null;
  if (context.type === 'record') {
    return context.record_label ?? context.record_title ?? null;
  }
  if (context.type === 'care') {
    return context.care_label ?? context.care_description ?? null;
  }
  return null;
}

/**
 * S9 — the owner lifecycle of the relation.
 *
 * A REMOVED Record or Care FREEZES its writes: its Files can be seen but
 * NOT detached.
 */
export function assetFileOwnerStatus(relation: AssetFileRelation): string | null {
  const context = relation.owner_context;
  if (!context) return null;
  if (context.type === 'record') return context.record_status ?? null;
  if (context.type === 'care') return context.care_status ?? null;
  return null;
}

/** True when the viewer may be opened for this state. */
export function assetFileStateAllowsViewer(state: AssetFileState): boolean {
  return state === 'available';
}

/** Human readable size, or null when the size is unknown. */
export function formatAssetFileSize(sizeBytes: number | null | undefined): string | null {
  if (typeof sizeBytes !== 'number' || !Number.isFinite(sizeBytes) || sizeBytes < 0) return null;
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = sizeBytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const rounded = value >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unitIndex]}`;
}

/** The icon of the row: a document when it is openable, a warning otherwise. */
const fileIconFor = (state: AssetFileState): 'document-text-outline' | 'alert-circle-outline' =>
  state === 'available' ? 'document-text-outline' : 'alert-circle-outline';

function AssetFileRowImpl({
  relation,
  onPress,
  onUnlink,
  canUnlink = true,
  showOwner = false,
  divider = false,
}: {
  relation: AssetFileRelation;
  /** Opens the real HomeCloud viewer (only for the `available` state). */
  onPress?: () => void;
  /** Detaches the File (the relation only). */
  onUnlink?: () => void;
  canUnlink?: boolean;
  /** S9: shows WHO owns the relation (the aggregated list). */
  showOwner?: boolean;
  /** Dibuja el separador con la fila anterior (la lista vive en una card). */
  divider?: boolean;
}) {
  const theme = useAppTheme();
  const { state, file } = relation;
  const badge = ASSET_FILE_STATE_BADGE[state];
  const canOpen = state === 'available' && typeof onPress === 'function';
  const title = state === 'missing' || !file ? ASSET_FILE_MISSING_LABEL : file.display_name ?? 'Archivo';
  const subtitle =
    state === 'missing' || !file
      ? null
      : [file.extension ? file.extension.toUpperCase() : null, formatAssetFileSize(file.size_bytes)]
          .filter(Boolean)
          .join(' · ');
  const ownerLabel = showOwner ? assetFileOwnerLabel(relation) : null;
  const ownerDetail = showOwner ? assetFileOwnerDetail(relation) : null;
  const isMuted = state !== 'available';

  // The accessible name carries the same information the row shows: name,
  // type/size, lifecycle state and owner. The state is never colour-only.
  const spoken = [
    title,
    subtitle,
    badge?.label,
    state === 'missing' ? ASSET_FILE_MISSING_LABEL : null,
    ownerLabel ? `${ownerLabel}${ownerDetail ? `, ${ownerDetail}` : ''}` : null,
  ]
    .filter(Boolean)
    .join('. ');

  return (
    <View
      style={[
        styles.row,
        divider ? { borderTopWidth: 1, borderTopColor: theme.colors.border.subtle } : null,
        isMuted ? styles.rowMuted : null,
      ]}
    >
      <InteractivePressable
        accessibilityRole="button"
        accessibilityLabel={spoken}
        accessibilityHint={canOpen ? 'Abre el archivo en HomeCloud' : undefined}
        accessibilityState={{ disabled: !canOpen }}
        disabled={!canOpen}
        onPress={() => onPress?.()}
        haptic="light"
        pressScale={0.98}
        style={styles.main}
      >
        <View accessible={false} importantForAccessibility="no">
          <HomePlusIcon
            name={fileIconFor(state)}
            size={iconSizes.action}
            color={isMuted ? colors.text.muted : colors.text.secondary}
          />
        </View>
        <View style={styles.textBlock}>
          <AppText
            variant="bodySmall"
            weight="600"
            numberOfLines={2}
            style={{ color: isMuted ? theme.colors.text.muted : theme.colors.text.primary }}
          >
            {title}
          </AppText>
          {subtitle ? (
            <AppText
              variant="caption"
              tone="secondary"
              numberOfLines={1}
              style={{ color: theme.colors.text.secondary }}
            >
              {subtitle}
            </AppText>
          ) : null}
          {badge ? (
            <AppText
              variant="caption"
              tone={badge.tone}
              weight="600"
              style={{
                color:
                  badge.tone === 'warning'
                    ? theme.colors.warning.text
                    : badge.tone === 'danger'
                      ? theme.colors.danger.text
                      : theme.colors.text.secondary,
              }}
            >
              {badge.label}
            </AppText>
          ) : null}
          {ownerLabel ? (
            <AppText
              variant="caption"
              tone="tertiary"
              numberOfLines={1}
              style={{ color: theme.colors.text.tertiary }}
            >
              {ownerLabel}
              {ownerDetail ? ` · ${ownerDetail}` : ''}
            </AppText>
          ) : null}
        </View>
      </InteractivePressable>
      {onUnlink && canUnlink ? (
        <InteractivePressable
          accessibilityRole="button"
          accessibilityLabel={`Quitar ${title}`}
          accessibilityHint="Lo saca de este activo; el archivo sigue en HomeCloud"
          onPress={() => onUnlink()}
          haptic="light"
          pressScale={0.95}
          style={styles.action}
        >
          <View accessible={false} importantForAccessibility="no">
            <HomePlusIcon name="close-circle-outline" size={iconSizes.action} color={theme.colors.text.secondary} />
          </View>
        </InteractivePressable>
      ) : null}
    </View>
  );
}

export const AssetFileRow = React.memo(AssetFileRowImpl);

const styles = StyleSheet.create({
  row: {
    minHeight: touchTargets.senior,
    paddingHorizontal: spacing[4],
    paddingVertical: spacing[3],
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
  rowMuted: {
    opacity: 0.72,
  },
  main: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
  textBlock: {
    flex: 1,
    minWidth: 0,
    gap: spacing[1],
  },
  action: {
    minWidth: touchTargets.normal,
    minHeight: touchTargets.normal,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
