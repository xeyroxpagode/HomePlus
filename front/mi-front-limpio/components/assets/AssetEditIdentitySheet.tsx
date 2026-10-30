import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import {
  createAssetsIntent,
  listCategories,
  mutations,
  type AssetCategory,
  type AssetDto,
  type AssetsFailure,
  type AssetsMutationIntent,
} from '../../services/assets';
import { AppButton } from '../ui/AppButton';
import { AppInput } from '../ui/AppInput';
import { AppText } from '../ui/AppText';
import { InteractivePressable } from '../ui/InteractivePressable';
import { colors, radius } from '../../constants/theme';
import { ASSET_IDENTIFIER_FIELDS } from './assetLabels';
import { AssetFormSheet } from './AssetSheet';
import { AssetsFailureBar } from './ErrorBar';

const IDENTIFIER_FIELDS = ASSET_IDENTIFIER_FIELDS;

export type AssetEditIdentitySheetProps = {
  visible: boolean;
  asset: AssetDto | null;
  onRequestClose: () => void;
  onSaved: (asset: AssetDto) => void;
  /** 409 stale: recargar el activo (decisión del usuario; el draft se conserva hasta entonces). */
  onReconcile?: () => void;
};

/**
 * O30/O31 — editar identidad por dimensión con concurrencia por snapshot
 * (expected_updated_at del asset cargado). Profile y categoría tienen sus
 * propios endpoints; acá se edita Nombre + metadatos de identidad.
 */
export function AssetEditIdentitySheet({
  visible,
  asset,
  onRequestClose,
  onSaved,
  onReconcile,
}: AssetEditIdentitySheetProps) {
  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? null;

  const [name, setName] = useState('');
  const [brand, setBrand] = useState('');
  const [model, setModel] = useState('');
  const [serial, setSerial] = useState('');
  const [identifiers, setIdentifiers] = useState<Record<string, string>>({});
  const [observedIdentity, setObservedIdentity] = useState<{
    brand: string | null;
    model: string | null;
    serial_number: string | null;
    identifiers: Record<string, string>;
  } | null>(null);
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<AssetsFailure | null>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [attempted, setAttempted] = useState(false);
  // Rename e Identity son decisiones distintas con bodies distintos: cada una
  // lleva SU Idempotency-Key. Compartir una sola clave hace que el backend
  // responda 409 idempotency_conflict a la segunda mutación del mismo submit.
  const [renameIntent, setRenameIntent] = useState<AssetsMutationIntent | undefined>(undefined);
  const [identityIntent, setIdentityIntent] = useState<AssetsMutationIntent | undefined>(undefined);

  React.useEffect(() => {
    if (visible && asset) {
      setName(asset.name);
      setBrand(asset.brand ?? '');
      setModel(asset.model ?? '');
      setSerial(asset.serial_number ?? '');
       setIdentifiers({ ...(asset.identifiers ?? {}) });
       setObservedIdentity({
         brand: asset.brand ?? null,
         model: asset.model ?? null,
         serial_number: asset.serial_number ?? null,
         identifiers: { ...(asset.identifiers ?? {}) },
       });
        setSelectedCategoryId(asset.category?.id ?? null);
      setNewCategoryName('');
      setFailure(null);
      setDirty(false);
      setAttempted(false);
      setConfirmDiscard(false);
      setRenameIntent(undefined);
      setIdentityIntent(undefined);
      if (accessToken) {
        void listCategories(accessToken)
          .then((response) => setCategories(response.categories ?? []))
          .catch(() => setCategories([]));
      }
    }
  }, [visible, asset, accessToken]);

  const requestClose = () => {
    if (pending) return;
    if (dirty) {
      setConfirmDiscard(true);
      return;
    }
    onRequestClose();
  };

  const handleDiscard = () => {
    setConfirmDiscard(false);
    onRequestClose();
  };

  const updateIdentifier = (key: string, value: string) => {
    setDirty(true);
    setIdentifiers((current) => ({ ...current, [key]: value }));
  };

  const nameError = attempted && name.trim().length === 0 ? 'El nombre no puede quedar vacío.' : null;

  const submit = async () => {
    if (!accessToken || !householdId || !asset || pending) return;
    setAttempted(true);
    if (name.trim().length === 0) return;
    setPending(true);
    setFailure(null);
    // Un fallo definitivo (4xx salvo 409/408/429) no escribió nada: el próximo
    // submit con el draft corregido es una decisión NUEVA y necesita una key
    // nueva (la key anterior quedó reservada con el body viejo y reproduciría
    // el 409 idempotency_conflict). Timeout/5xx SÍ conservan la key (§13).
    const dropIntentIfFinal = (failure: AssetsFailure, clear: () => void) => {
      if (failure.kind === 'definitive' || failure.kind === 'forbidden') clear();
    };
    const activeRenameIntent = renameIntent ?? createAssetsIntent('asset.rename');
    if (!renameIntent) setRenameIntent(activeRenameIntent);
    const activeIdentityIntent = identityIntent ?? createAssetsIntent('asset.identity');
    if (!identityIntent) setIdentityIntent(activeIdentityIntent);

    const cleanedIdentifiers = Object.fromEntries(
      Object.entries(identifiers).filter(([, value]) => value.trim().length > 0),
    );

    // Nombre por su endpoint (concurrencia del asset); identidad por el suyo;
    // categoría por el suyo (O31). Cada dimensión falla o confirma sola.
    const nameChanged = name.trim() !== asset.name;
    const identityChanged =
      (brand.trim() || null) !== asset.brand ||
      (model.trim() || null) !== asset.model ||
      (serial.trim() || null) !== asset.serial_number ||
      JSON.stringify(cleanedIdentifiers) !== JSON.stringify(asset.identifiers ?? {});
    const categoryChanged = selectedCategoryId !== (asset.category?.id ?? null);

    let latest: AssetDto | null = null;

    if (nameChanged) {
      const outcome = await mutations.renameAsset(
        accessToken,
        householdId,
        asset.id,
        { name: name.trim(), expected_updated_at: asset.updated_at },
        { intent: activeRenameIntent },
      );
      if (!outcome.ok) {
        setPending(false);
        setFailure(outcome.failure);
        dropIntentIfFinal(outcome.failure, () => setRenameIntent(undefined));
        return;
      }
      latest = outcome.data.asset;
    }

    if (identityChanged || latest) {
      const snapshot = observedIdentity ?? {
        brand: asset.brand ?? null,
        model: asset.model ?? null,
        serial_number: asset.serial_number ?? null,
        identifiers: { ...(asset.identifiers ?? {}) },
      };
      const outcome = await mutations.updateIdentity(
        accessToken,
        householdId,
        asset.id,
        {
          brand: brand.trim() || null,
          model: model.trim() || null,
          serial_number: serial.trim() || null,
          identifiers: cleanedIdentifiers,
          expected_identity: snapshot,
        },
        { intent: activeIdentityIntent },
      );
      if (!outcome.ok) {
        setPending(false);
        setFailure(outcome.failure);
        // El rename ya confirmado queda protegido por su propia key (replay):
        // sólo se descarta el intent del slot que falló de forma definitiva.
        dropIntentIfFinal(outcome.failure, () => setIdentityIntent(undefined));
        return;
      }
      latest = outcome.data.asset;
    }

    if (categoryChanged) {
      const outcome = await mutations.setCategory(
        accessToken,
        householdId,
        asset.id,
        {
          category_id: selectedCategoryId,
          expected_category_id: asset.category?.id ?? null,
        },
      );
      if (!outcome.ok) {
        setPending(false);
        setFailure(outcome.failure);
        return;
      }
      latest = outcome.data.asset;
    }

    setPending(false);
    // Ciclo completo confirmado: un submit posterior (si el sheet sigue abierto)
    // es una decisión nueva y necesita intents nuevos.
    setRenameIntent(undefined);
    setIdentityIntent(undefined);
    if (latest) {
      setDirty(false);
      onSaved(latest);
    } else {
      onSaved(asset);
    }
  };

  const identifierFields = asset ? IDENTIFIER_FIELDS[asset.profile] : [];

  return (
    <AssetFormSheet
      visible={visible}
      title="Editar identidad"
      subtitle={asset?.name}
      onRequestClose={requestClose}
      closeDisabled={pending}
      footer={
        <View style={styles.footer}>
          <AssetsFailureBar
            failure={failure}
            onRetry={() => void submit()}
            onReconcile={() => {
              if (onReconcile) {
                onReconcile();
              } else {
                requestClose();
              }
            }}
          />
          <AppButton
            title={pending ? 'Guardando…' : 'Guardar cambios'}
            onPress={() => void submit()}
            loading={pending}
            accessibilityLabel="Guardar cambios de identidad"
          />
        </View>
      }
    >
      <ScrollView contentContainerStyle={styles.form}>
        <AppInput
          label="Nombre"
          value={name}
          onChangeText={(text) => {
            setDirty(true);
            setName(text);
          }}
          errorText={nameError ?? undefined}
          accessibilityLabel="Nombre del activo"
        />
        <AppInput
          label="Marca (opcional)"
          value={brand}
          onChangeText={(text) => {
            setDirty(true);
            setBrand(text);
          }}
          placeholder="Ej: Trek"
          accessibilityLabel="Marca"
        />
        <AppInput
          label="Modelo (opcional)"
          value={model}
          onChangeText={(text) => {
            setDirty(true);
            setModel(text);
          }}
          placeholder="Ej: FX 3"
          accessibilityLabel="Modelo"
        />
        <AppInput
          label="Número de serie (opcional)"
          value={serial}
          onChangeText={(text) => {
            setDirty(true);
            setSerial(text);
          }}
          placeholder="Ej: W123456789"
          accessibilityLabel="Número de serie"
        />
        {identifierFields.map((field) => (
          <AppInput
            key={field.key}
            label={field.label}
            value={identifiers[field.key] ?? ''}
            onChangeText={(text) => updateIdentifier(field.key, text)}
            placeholder={field.placeholder}
            accessibilityLabel={field.label}
          />
        ))}

        <View style={styles.group}>
          <AppText variant="caption" weight="700" tone="secondary">
            Categoría
          </AppText>
          <View style={styles.categoryWrap}>
            {categories.map((category) => (
              <InteractivePressable
                key={category.id ? `category:${category.id}` : `suggested:${category.name.trim().toLowerCase()}`}
                accessibilityRole="button"
                accessibilityLabel={category.name}
                accessibilityState={{
                  selected: category.id !== null && selectedCategoryId === category.id,
                }}
                onPress={() => {
                  if (category.id === null) return;
                  setDirty(true);
                  setSelectedCategoryId((current) => (current === category.id ? null : category.id));
                }}
                haptic="light"
                pressScale={0.98}
                style={[
                  styles.categoryChip,
                  category.id !== null && selectedCategoryId === category.id && styles.categoryChipSelected,
                ]}
              >
                <AppText variant="caption" weight="600" numberOfLines={2}>
                  {category.name}
                </AppText>
              </InteractivePressable>
            ))}
          </View>
          <AppInput
            label="Crear categoría nueva (opcional)"
            value={newCategoryName}
            onChangeText={(text) => {
              setDirty(true);
              setNewCategoryName(text);
            }}
            placeholder="Ej: Herramientas"
            accessibilityLabel="Nombre de la categoría nueva"
          />
          {newCategoryName.trim().length > 0 ? (
            <AppButton
              title="Crear y asignar"
              size="sm"
              variant="secondary"
              onPress={async () => {
                if (!accessToken || !householdId || pending) return;
                setPending(true);
                const outcome = await mutations.createCategory(accessToken, householdId, {
                  name: newCategoryName.trim(),
                });
                setPending(false);
                if (outcome.ok) {
                  setCategories((current) =>
                    current.some((c) => c.id === outcome.data.category.id)
                      ? current
                      : [...current, outcome.data.category],
                  );
                  setSelectedCategoryId(outcome.data.category.id);
                  setNewCategoryName('');
                  setDirty(true);
                } else {
                  setFailure(outcome.failure);
                }
              }}
              accessibilityLabel="Crear categoría nueva y asignarla"
            />
          ) : null}
        </View>
      </ScrollView>

      {confirmDiscard ? (
        <View style={styles.discard}>
          <AppText variant="bodySmall" tone="secondary">
            Tenés cambios sin guardar. Si salís ahora, se pierden.
          </AppText>
          <View style={styles.discardActions}>
            <AppButton
              variant="secondary"
              size="sm"
              title="Seguir editando"
              onPress={() => setConfirmDiscard(false)}
            />
            <AppButton variant="danger" size="sm" title="Descartar cambios" onPress={handleDiscard} />
          </View>
        </View>
      ) : null}
    </AssetFormSheet>
  );
}

const styles = StyleSheet.create({
  footer: { gap: 8 },
  error: { marginBottom: 4 },
  form: { gap: 14, paddingBottom: 24 },
  group: { gap: 7 },
  categoryWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  categoryChip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border.default,
    backgroundColor: colors.surface.soft,
  },
  categoryChipSelected: {
    borderColor: colors.brand,
    backgroundColor: colors.brandSoft,
  },
  discard: {
    gap: 10,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.border.subtle,
  },
  discardActions: { flexDirection: 'row', gap: 10 },
});
