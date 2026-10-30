import React, { useRef, useState } from 'react';
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import { useAssetsList } from '../../hooks/assets/useAssetsData';
import {
  createAssetsIntent,
  holderValueOf,
  mutations,
  placementValueOf,
  type AssetDto,
  type AssetsFailure,
  type AssetsMutationIntent,
} from '../../services/assets';
import { AppButton } from '../ui/AppButton';
import { AppText } from '../ui/AppText';
import { InteractivePressable } from '../ui/InteractivePressable';
import { colors, radius, spacing, touchTargets, typography } from '../../constants/theme';
import { AssetActionMenu, AssetFormSheet } from './AssetSheet';
import { AssetsFailureBar } from './ErrorBar';
import { describeHolder, describePlacement, describeResponsible } from './assetLabels';

export type AssetContextSheetProps = {
  visible: boolean;
  asset: AssetDto | null;
  /** Proyección de capabilities: sin assets.contribute no se puede escribir contexto. */
  canContribute: boolean;
  onRequestClose: () => void;
  onSaved: (asset: AssetDto) => void;
};

type Dimension = 'responsible' | 'holder' | 'placement';

/**
 * O26–O28 — tres dimensiones INDEPENDIENTES: cada PATCH tiene su propio
 * pending/error/éxito localizado. Sin "Guardar todo" que simule atomicidad.
 * PROPERTY no admite Holder/Placement operacional: el backend lo prohíbe y
 * aquí se explica en lugar de mostrar la opción.
 */
export function AssetContextSheet({ visible, asset, canContribute, onRequestClose, onSaved }: AssetContextSheetProps) {
  const { session } = useAuth();
  const { currentHousehold, members } = useHousehold();
  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? null;

  const [picker, setPicker] = useState<Dimension | null>(null);
  const [pendingDimension, setPendingDimension] = useState<Dimension | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Dimension, AssetsFailure>>>({});
  const [intent, setIntent] = useState<AssetsMutationIntent | undefined>(undefined);
  const retryLast = useRef<(() => void) | null>(null);

  // O28 Picker Property: propiedades reales del household (paginado).
  const propertyList = useAssetsList(accessToken, householdId, 'normal', {
    profile: 'PROPERTY',
  });

  // Externo para Holder.
  const [externalLabel, setExternalLabel] = useState('');
  const [confirmExternal, setConfirmExternal] = useState(false);

  React.useEffect(() => {
    if (visible) {
      setPicker(null);
      setPendingDimension(null);
      setErrors({});
      setExternalLabel('');
      setConfirmExternal(false);
      setIntent(undefined);
    }
  }, [visible]);

  const getOrCreateIntent = () => {
    const active = intent ?? createAssetsIntent('asset.context');
    if (!intent) setIntent(active);
    return active;
  };

  const runDimension = async (
    dimension: Dimension,
    execute: () => Promise<{ ok: true; data: { asset: AssetDto } } | { ok: false; failure: AssetsFailure }>,
  ) => {
    if (!accessToken || !householdId || !asset || pendingDimension) return;
    retryLast.current = () => void runDimension(dimension, execute);
    setPendingDimension(dimension);
    setErrors((current) => ({ ...current, [dimension]: undefined }));
    const outcome = await execute();
    setPendingDimension(null);
    if (outcome.ok) {
      // El cambio confirmó: el próximo cambio de contexto (el sheet sigue
      // abierto) es una decisión NUEVA. Reutilizar la misma Idempotency-Key
      // con un body distinto haría que el backend responda 409
      // idempotency_conflict.
      setIntent(undefined);
      onSaved(outcome.data.asset);
      setPicker(null);
    } else {
      setErrors((current) => ({ ...current, [dimension]: outcome.failure }));
      // Fallo definitivo (nada escrito): el próximo intento con el draft
      // corregido es una decisión nueva y necesita una key nueva. Los fallos
      // transitorios/desconocidos conservan la key (§13).
      if (outcome.failure.kind === 'definitive' || outcome.failure.kind === 'forbidden') {
        setIntent(undefined);
      }
    }
  };

  const setResponsible = (memberId: string | null) =>
    runDimension('responsible', () =>
      mutations.setResponsible(accessToken!, householdId!, asset!.id, {
        responsible_member_id: memberId,
        expected_responsible_member_id: asset!.responsible?.member_id ?? null,
      }, {
        intent: getOrCreateIntent(),
      }),
    );

  const setHolderMember = (memberId: string) =>
    runDimension('holder', () =>
      mutations.setHolder(accessToken!, householdId!, asset!.id, {
        holder: { member_id: memberId },
        expected_holder: holderValueOf(asset!.holder),
      }, {
        intent: getOrCreateIntent(),
      }),
    );

  const setHolderExternal = () => {
    if (externalLabel.trim().length === 0) return;
    setConfirmExternal(false);
    void runDimension('holder', () =>
      mutations.setHolder(accessToken!, householdId!, asset!.id, {
        holder: { external_label: externalLabel.trim() },
        expected_holder: holderValueOf(asset!.holder),
      }, {
        intent: getOrCreateIntent(),
      }),
    );
  };

  const clearHolder = () =>
    runDimension('holder', () =>
      mutations.setHolder(accessToken!, householdId!, asset!.id, {
        holder: null,
        expected_holder: holderValueOf(asset!.holder),
      }, {
        intent: getOrCreateIntent(),
      }),
    );

  const setPlacementProperty = (propertyId: string) =>
    runDimension('placement', () =>
      mutations.setPlacement(accessToken!, householdId!, asset!.id, {
        placement: { property_asset_id: propertyId },
        expected_placement: placementValueOf(asset!.placement),
      }, {
        intent: getOrCreateIntent(),
      }),
    );

  const setPlacementText = () => {
    if (externalLabel.trim().length === 0) return;
    setConfirmExternal(false);
    void runDimension('placement', () =>
      mutations.setPlacement(accessToken!, householdId!, asset!.id, {
        placement: { external_text: externalLabel.trim() },
        expected_placement: placementValueOf(asset!.placement),
      }, {
        intent: getOrCreateIntent(),
      }),
    );
  };

  const clearPlacement = () =>
    runDimension('placement', () =>
      mutations.setPlacement(accessToken!, householdId!, asset!.id, {
        placement: null,
        expected_placement: placementValueOf(asset!.placement),
      }, {
        intent: getOrCreateIntent(),
      }),
    );

  if (!asset) return null;

  const isProperty = asset.profile === 'PROPERTY';
  const holderDescription = describeHolder(asset.holder) ?? 'Sin especificar quién lo tiene';
  const placementDescription = describePlacement(asset.placement) ?? 'Sin especificar dónde está';
  const responsibleDescription = describeResponsible(asset.responsible) ?? 'Sin responsable';

  return (
    <>
      <AssetActionMenu
        visible={visible && picker === null}
        title="Personas y ubicación"
        subtitle={asset.name}
        onRequestClose={onRequestClose}
        closeDisabled={pendingDimension !== null}
        options={[
          {
            key: 'responsible',
            label: 'Responsable',
            description: responsibleDescription,
            icon: 'person-outline',
            disabled: !canContribute || pendingDimension !== null,
            disabledReason: canContribute ? undefined : 'Necesitás permiso para editar el contexto',
            onSelect: () => setPicker('responsible'),
          },
          {
            key: 'holder',
            label: 'Quién lo tiene',
            description: isProperty ? 'Una propiedad no se asigna a una persona' : holderDescription,
            icon: 'hand-right-outline',
            disabled: isProperty || !canContribute || pendingDimension !== null,
            disabledReason: isProperty
              ? 'Una propiedad no se asigna a una persona'
              : canContribute
                ? undefined
                : 'Necesitás permiso para editar el contexto',
            onSelect: () => setPicker('holder'),
          },
          {
            key: 'placement',
            label: 'Dónde está',
            description: isProperty ? 'Una propiedad no se ubica dentro de otra' : placementDescription,
            icon: 'location-outline',
            disabled: isProperty || !canContribute || pendingDimension !== null,
            disabledReason: isProperty
              ? 'Una propiedad no se ubica dentro de otra'
              : canContribute
                ? undefined
                : 'Necesitás permiso para editar el contexto',
            onSelect: () => setPicker('placement'),
          },
        ]}
      />

      {/* O27 Picker miembro — Responsible */}
      {picker === 'responsible' ? (
        <AssetFormSheet
          visible
          title="Responsable"
          subtitle="Quien responde por este activo"
          onRequestClose={() => setPicker(null)}
          closeDisabled={pendingDimension === 'responsible'}
          footer={
            <AssetsFailureBar
              failure={errors.responsible ?? null}
              onRetry={() => retryLast.current?.()}
            />
          }
        >
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            <View style={styles.optionList}>
              {members.map((member) => (
                <ContextOption
                  key={member.id}
                  label={member.user?.nombre ?? 'Miembro'}
                  selected={asset.responsible?.member_id === member.id}
                  pending={pendingDimension === 'responsible'}
                  onPress={() => setResponsible(member.id)}
                />
              ))}
              <ContextOption
                label="Sin responsable"
                selected={!asset.responsible}
                pending={pendingDimension === 'responsible'}
                onPress={() => setResponsible(null)}
              />
            </View>
          </ScrollView>
        </AssetFormSheet>
      ) : null}

      {/* O27 Picker miembro/externo — Holder */}
      {picker === 'holder' ? (
        <AssetFormSheet
          visible
          title="Quién lo tiene"
          subtitle="Un miembro del hogar o alguien de afuera"
          onRequestClose={() => setPicker(null)}
          closeDisabled={pendingDimension === 'holder'}
          footer={
            <AssetsFailureBar
              failure={errors.holder ?? null}
              onRetry={() => retryLast.current?.()}
            />
          }
        >
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            <View style={styles.optionList}>
              {members.map((member) => (
                <ContextOption
                  key={member.id}
                  label={member.user?.nombre ?? 'Miembro'}
                  selected={asset.holder?.kind === 'member' && asset.holder.member_id === member.id}
                  pending={pendingDimension === 'holder'}
                  onPress={() => setHolderMember(member.id)}
                />
              ))}
              <ContextOption
                label="Quitar asignación"
                selected={!asset.holder || asset.holder.kind === 'none'}
                pending={pendingDimension === 'holder'}
                onPress={clearHolder}
              />
            </View>
            <View style={styles.externalBlock}>
              <AppText variant="caption" weight="700" tone="secondary">
                Alguien de afuera del hogar
              </AppText>
              <TextInput
                value={externalLabel}
                onChangeText={setExternalLabel}
                placeholder="Ej: El vecino de al lado"
                placeholderTextColor={colors.text.muted}
                style={styles.externalInput}
                accessibilityLabel="Alguien de afuera del hogar"
                accessibilityHint="Escribí el nombre de quien tiene el activo y tocá Asignar"
                returnKeyType="done"
              />
              <AppButton
                title="Asignar"
                size="sm"
                disabled={externalLabel.trim().length === 0}
                onPress={() => setConfirmExternal(true)}
                accessibilityLabel="Asignar a persona externa"
                accessibilityHint={
                  externalLabel.trim().length === 0
                    ? 'Escribí primero un nombre'
                    : 'Asigna el activo a esa persona'
                }
              />
            </View>
            {confirmExternal ? (
              <View style={styles.confirmRow}>
                <AppButton
                  variant="secondary"
                  size="sm"
                  title="Cancelar"
                  onPress={() => setConfirmExternal(false)}
                />
                <AppButton size="sm" title="Confirmar" onPress={() => void setHolderExternal()} />
              </View>
            ) : null}
          </ScrollView>
        </AssetFormSheet>
      ) : null}

      {/* O28 Picker Property / texto libre — Placement */}
      {picker === 'placement' ? (
        <AssetFormSheet
          visible
          title="Dónde está"
          subtitle="Una propiedad del hogar o una referencia libre"
          onRequestClose={() => setPicker(null)}
          closeDisabled={pendingDimension === 'placement'}
          footer={
            <AssetsFailureBar
              failure={errors.placement ?? null}
              onRetry={() => retryLast.current?.()}
            />
          }
        >
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            <View style={styles.optionList}>
              {propertyList.loading && propertyList.assets.length === 0 ? (
                <AppText variant="bodySmall" tone="tertiary">
                  Cargando propiedades…
                </AppText>
              ) : propertyList.error ? (
                <AppText variant="bodySmall" tone="danger">
                  No pudimos cargar las propiedades del hogar.
                </AppText>
              ) : propertyList.assets.length === 0 ? (
                <AppText variant="bodySmall" tone="tertiary">
                  No hay propiedades cargadas en el hogar.
                </AppText>
              ) : (
                propertyList.assets.map((property) => (
                  <ContextOption
                    key={property.id}
                    label={property.name}
                    selected={
                      asset.placement?.kind === 'property' &&
                      asset.placement.property_asset_id === property.id
                    }
                    pending={pendingDimension === 'placement'}
                    onPress={() => setPlacementProperty(property.id)}
                  />
                ))
              )}
              <ContextOption
                label="Quitar ubicación"
                selected={!asset.placement || asset.placement.kind === 'none'}
                pending={pendingDimension === 'placement'}
                onPress={clearPlacement}
              />
            </View>
            <View style={styles.externalBlock}>
              <AppText variant="caption" weight="700" tone="secondary">
                Otra referencia
              </AppText>
              <TextInput
                value={externalLabel}
                onChangeText={setExternalLabel}
                placeholder="Ej: Casilla del club"
                placeholderTextColor={colors.text.muted}
                style={styles.externalInput}
                accessibilityLabel="Otra referencia"
                accessibilityHint="Escribí una referencia de ubicación y tocá Guardar referencia"
                returnKeyType="done"
              />
              <AppButton
                title="Guardar referencia"
                size="sm"
                disabled={externalLabel.trim().length === 0}
                onPress={() => setPlacementText()}
                accessibilityLabel="Guardar referencia de ubicación"
                accessibilityHint={
                  externalLabel.trim().length === 0
                    ? 'Escribí primero una referencia'
                    : 'Guarda la referencia de ubicación'
                }
              />
            </View>
          </ScrollView>
        </AssetFormSheet>
      ) : null}
    </>
  );
}

function ContextOption({
  label,
  selected,
  pending,
  onPress,
}: {
  label: string;
  selected: boolean;
  pending: boolean;
  onPress: () => void;
}) {
  return (
    <InteractivePressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected, disabled: pending }}
      disabled={pending}
      onPress={onPress}
      haptic="light"
      pressScale={0.98}
      style={[
        styles.option,
        selected && styles.optionSelected,
        pending && styles.optionPending,
      ]}
    >
      <AppText variant="bodySmall" weight={selected ? '700' : '500'} numberOfLines={2}>
        {label}
      </AppText>
    </InteractivePressable>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 0,
  },
  scrollContent: {
    paddingBottom: spacing[2],
  },
  optionList: { gap: spacing[2], paddingBottom: spacing[4] },
  option: {
    minHeight: touchTargets.senior,
    paddingHorizontal: spacing[4],
    justifyContent: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border.default,
    backgroundColor: colors.surface.card,
  },
  optionSelected: {
    borderColor: colors.brand,
    backgroundColor: colors.brandSoft,
  },
  optionPending: { opacity: 0.6 },
  externalBlock: { gap: spacing[2], paddingTop: spacing[2], paddingBottom: spacing[4] },
  externalInput: {
    minHeight: touchTargets.senior,
    borderWidth: 1,
    borderColor: colors.border.default,
    borderRadius: radius.md,
    backgroundColor: colors.surface.card,
    paddingHorizontal: spacing[4],
    paddingVertical: spacing[3],
    color: colors.text.primary,
    fontSize: typography.body.fontSize,
  },
  confirmRow: { flexDirection: 'row', gap: spacing[2], paddingBottom: spacing[3] },
});
