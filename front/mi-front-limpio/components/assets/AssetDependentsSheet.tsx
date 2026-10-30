/**
 * HOMePLUS Assets — S9: the REVIEW surface of a lifecycle blocker (O33).
 *
 * A PROPERTY with operational dependents cannot be archived nor moved to the
 * trash until those dependents are reconciled explicitly. The backend answers
 * a typed 409 with the list of blockers; this sheet is the DESTINATION of
 * that blocker: the user can SEE what blocks the action and OPEN the exact
 * dependent where the reconciliation happens.
 *
 * HARD RULES (frozen):
 *   - It NEVER mutates a dependent: no cascade, no reassignment, no
 *     auto-archive. The user resolves each dependent by hand.
 *   - It NEVER changes the blocker semantics: the list shown is exactly the
 *     one the backend reported.
 *   - The dependents are same-Household Assets the caller can already list:
 *     nothing restricted is disclosed here.
 *   - When the list is empty (a stale payload) the sheet says so honestly
 *     instead of inventing a blocker.
 */

import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { AppButton } from '../ui/AppButton';
import { AppText } from '../ui/AppText';
import { HomePlusIcon } from '../../constants/icons';
import { InteractivePressable } from '../ui/InteractivePressable';
import { AssetFormSheet } from './AssetSheet';
import { LIFECYCLE_LABEL } from './assetLabels';
import { useAppTheme } from '../../context/AppThemeContext';
import { radius, spacing, touchTargets } from '../../constants/theme';
import type { AssetDependent } from '../../services/assets/errors';

const LIFECYCLE_FALLBACK: Record<string, string> = {
  ACTIVE: 'Activo',
  INACTIVE: 'Inactivo',
  ARCHIVED: 'Archivado',
  TRASH: 'En la papelera',
};

const lifecycleLabel = (status: string | null): string => {
  if (!status) return 'Activo';
  const known = LIFECYCLE_LABEL[status as keyof typeof LIFECYCLE_LABEL];
  if (known) return known;
  return LIFECYCLE_FALLBACK[status] ?? status;
};

export function AssetDependentsSheet({
  visible,
  dependents,
  dependentCount,
  onRequestClose,
  onOpenDependent,
}: {
  visible: boolean;
  /** The blocking dependents, exactly as the backend reported them. */
  dependents: readonly AssetDependent[];
  /** The EXACT total (it can be bigger than the listed rows). */
  dependentCount?: number | null;
  onRequestClose: () => void;
  /** Opens the dependent Asset (where the reconciliation happens). */
  onOpenDependent?: (assetId: string) => void;
}) {
  const theme = useAppTheme();
  const total = typeof dependentCount === 'number' ? dependentCount : dependents.length;
  const listed = dependents.length;
  const hidden = Math.max(total - listed, 0);

  return (
    <AssetFormSheet
      visible={visible}
      title="Revisar dependientes"
      subtitle={
        total === 1
          ? '1 activo bloquea esta operación'
          : `${total} activos bloquean esta operación`
      }
      onRequestClose={onRequestClose}
      footer={
        <AppButton
          variant="secondary"
          title="Volver"
          onPress={onRequestClose}
          accessibilityLabel="Volver sin cambiar nada"
        />
      }
    >
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <AppText variant="bodySmall" tone="secondary" style={styles.explainer}>
          Estos activos están ubicados acá, así que esta propiedad no se puede archivar ni mover a la
          papelera todavía. Abrí cada uno y reconciliá su ubicación: nada se cambia solo.
        </AppText>

        {listed === 0 ? (
          <AppText variant="bodySmall" tone="secondary" style={styles.explainer}>
            {hidden > 0
              ? `Hay ${hidden} bloqueos y no pudimos mostrar el detalle. Volvé a intentar la operación para revisarlos.`
              : 'No hay dependientes detallados. Volvé a intentar la operación para comprobar el estado actual.'}
          </AppText>
        ) : (
          <View style={styles.list}>
            {dependents.map((dependent) => {
              const name = dependent.name ?? 'Activo sin nombre';
              const lifecycle = lifecycleLabel(dependent.lifecycle_status);
              return (
                <InteractivePressable
                  key={dependent.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Abrir ${name}. ${lifecycle}`}
                  accessibilityHint="Abre el activo que bloquea la operación para reconciliar su ubicación"
                  onPress={() => onOpenDependent?.(dependent.id)}
                  haptic="light"
                  pressScale={0.98}
                  style={[
                    styles.row,
                    {
                      backgroundColor: theme.colors.surface.soft,
                      borderColor: theme.colors.border.default,
                    },
                  ]}
                >
                  <View accessible={false} importantForAccessibility="no">
                    <HomePlusIcon
                      name="cube-outline"
                      size={20}
                      color={theme.colors.text.secondary}
                    />
                  </View>
                  <View style={{ flex: 1, minWidth: 0, gap: spacing[1] }}>
                    <AppText
                      variant="bodySmall"
                      weight="600"
                      numberOfLines={2}
                      style={{ color: theme.colors.text.primary }}
                    >
                      {name}
                    </AppText>
                    <AppText
                      variant="caption"
                      tone="tertiary"
                      style={{ color: theme.colors.text.tertiary }}
                    >
                      {lifecycle}
                    </AppText>
                  </View>
                  {onOpenDependent ? (
                    <AppText variant="caption" weight="700" tone="brand">
                      Abrir ›
                    </AppText>
                  ) : null}
                </InteractivePressable>
              );
            })}
          </View>
        )}

        {hidden > 0 && listed > 0 ? (
          <AppText variant="caption" tone="tertiary">
            Se muestran {listed} de {total}. Reconciliá los que veas y volvé a intentar la operación
            para ver el resto.
          </AppText>
        ) : null}
      </ScrollView>
    </AssetFormSheet>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 0,
  },
  scrollContent: {
    gap: spacing[2],
    paddingBottom: spacing[2],
  },
  explainer: { paddingBottom: spacing[3] },
  list: { gap: spacing[2], paddingBottom: spacing[4] },
  row: {
    minHeight: touchTargets.senior,
    paddingHorizontal: spacing[4],
    paddingVertical: spacing[3],
    borderRadius: radius.lg,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
});
