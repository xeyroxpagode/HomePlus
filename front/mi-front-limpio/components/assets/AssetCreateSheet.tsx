import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import {
  createAssetsIntent,
  mutations,
  listCategories,
  type AssetCategory,
  type AssetProfile,
  type AssetsFailure,
  type AssetsMutationIntent,
  type CreateAssetPayload,
} from '../../services/assets';
import { ASSET_PROFILES } from '../../services/assets/types';
import { AppButton } from '../ui/AppButton';
import { AppInput } from '../ui/AppInput';
import { AppText } from '../ui/AppText';
import { InteractivePressable } from '../ui/InteractivePressable';
import { colors, radius, spacing, touchTargets } from '../../constants/theme';
import { ASSET_IDENTIFIER_FIELDS, PROFILE_LABEL } from './assetLabels';
import { AssetFormSheet } from './AssetSheet';
import { AssetsFailureBar } from './ErrorBar';

export type AssetCreateSheetProps = {
  visible: boolean;
  onRequestClose: () => void;
  onCreated: (assetId: string) => void;
};

type Draft = {
  name: string;
  profile: AssetProfile;
  brand: string;
  model: string;
  serial: string;
  identifiers: Record<string, string>;
  category_id: string | null;
  category_name: string;
};

const PROFILE_IDENTIFIER_FIELDS = ASSET_IDENTIFIER_FIELDS;

const emptyDraft = (): Draft => ({
  name: '',
  profile: 'STANDARD',
  brand: '',
  model: '',
  serial: '',
  identifiers: {},
  category_id: null,
  category_name: '',
});

export function AssetCreateSheet({ visible, onRequestClose, onCreated }: AssetCreateSheetProps) {
  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? null;

  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<AssetsFailure | null>(null);
  /** Identidad del intento: se conserva y reutiliza en retry (nunca se regenera). */
  const [intent, setIntent] = useState<AssetsMutationIntent | undefined>(undefined);
  const [dirty, setDirty] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const [attempted, setAttempted] = useState(false);
  const nameError =
    attempted && draft.name.trim().length === 0 ? 'Ponele un nombre al activo.' : null;

  const loadCategories = React.useCallback(async () => {
    if (!accessToken || categoriesLoaded) return;
    try {
      const response = await listCategories(accessToken);
      setCategories(response.categories ?? []);
      setCategoriesLoaded(true);
    } catch {
      setCategoriesLoaded(true);
    }
  }, [accessToken, categoriesLoaded]);

  React.useEffect(() => {
    if (visible) void loadCategories();
  }, [visible, loadCategories]);

  const requestClose = () => {
    if (pending) return; // O38: nunca descartar una operación enviada con resultado incierto
    if (dirty) {
      setConfirmDiscard(true);
      return;
    }
    onRequestClose();
  };

  const handleDiscard = () => {
    setConfirmDiscard(false);
    setDirty(false);
    setAttempted(false);
    setDraft(emptyDraft());
    setFailure(null);
    setIntent(undefined);
    onRequestClose();
  };

  const updateIdentifier = (key: string, value: string) => {
    setDirty(true);
    setDraft((current) => ({
      ...current,
      identifiers: { ...current.identifiers, [key]: value },
    }));
  };

  const submit = async () => {
    if (!accessToken || !householdId || pending) return;
    setAttempted(true);
    if (draft.name.trim().length === 0) return;
    setPending(true);
    setFailure(null);
    // La identidad del intento se crea una vez y se reutiliza en cada retry:
    // regenerarla tras timeout/5xx duplicaría el activo (Target §13).
    const activeIntent = intent ?? createAssetsIntent('asset.create');
    if (!intent) setIntent(activeIntent);
    const identifiers = Object.fromEntries(
      Object.entries(draft.identifiers).filter(([, value]) => value.trim().length > 0),
    );
    const payload: CreateAssetPayload = {
      name: draft.name.trim(),
      profile: draft.profile,
      ...(draft.brand.trim() ? { brand: draft.brand.trim() } : {}),
      ...(draft.model.trim() ? { model: draft.model.trim() } : {}),
      ...(draft.serial.trim() ? { serial_number: draft.serial.trim() } : {}),
      ...(Object.keys(identifiers).length > 0 ? { identifiers } : {}),
      ...(draft.category_id ? { category_id: draft.category_id } : {}),
    };
    const outcome = await mutations.createAsset(accessToken, householdId, payload, {
      intent: activeIntent,
    });
    if (outcome.ok) {
      setPending(false);
      setDirty(false);
      setAttempted(false);
      setDraft(emptyDraft());
      setIntent(undefined);
      onCreated(outcome.data.asset.id);
      return;
    }
    setPending(false);
    setFailure(outcome.failure);
    // Fallo definitivo (nada escrito): corregir el draft y volver a mandar es
    // una decisión NUEVA y necesita una Idempotency-Key nueva. La key vieja
    // quedó reservada con el body del intento fallido y un body distinto
    // recibiría 409 idempotency_conflict. Timeout/5xx conservan la key (§13).
    if (outcome.failure.kind === 'definitive' || outcome.failure.kind === 'forbidden') {
      setIntent(undefined);
    }
  };

  const identifierFields = PROFILE_IDENTIFIER_FIELDS[draft.profile];

  return (
    <AssetFormSheet
      visible={visible}
      title="Nuevo activo"
      subtitle="Guardá lo que importa"
      onRequestClose={requestClose}
      closeDisabled={pending}
      footer={
        <View style={styles.footer}>
          <AssetsFailureBar failure={failure} onRetry={() => void submit()} />
          <AppButton
            title={pending ? 'Guardando…' : 'Crear activo'}
            onPress={() => void submit()}
            loading={pending}
            disabled={pending}
            accessibilityLabel="Crear activo"
            accessibilityHint={
              draft.name.trim().length === 0 ? 'Escribí primero un nombre' : undefined
            }
          />
        </View>
      }
    >
      <ScrollView style={{ flexShrink: 0 }} contentContainerStyle={styles.form}>
        <AppInput
          label="Nombre"
          value={draft.name}
          onChangeText={(text) => {
            setDirty(true);
            setDraft((c) => ({ ...c, name: text }));
          }}
          placeholder="Ej: Bicicleta de Tomi"
          errorText={nameError ?? undefined}
          accessibilityLabel="Nombre del activo"
        />

        <View style={styles.group}>
          <AppText variant="caption" weight="700" tone="secondary">
            Tipo
          </AppText>
          <View style={styles.profileGrid}>
            {ASSET_PROFILES.map((profile) => (
              <InteractivePressable
                key={profile}
                accessibilityRole="button"
                accessibilityLabel={PROFILE_LABEL[profile]}
                accessibilityState={{ selected: draft.profile === profile }}
                onPress={() => {
                  setDirty(true);
                  setDraft((c) => ({ ...c, profile, identifiers: {} }));
                }}
                haptic="light"
                pressScale={0.98}
                style={[
                  styles.profileChip,
                  draft.profile === profile && styles.profileChipSelected,
                ]}
              >
                <AppText
                  variant="bodySmall"
                  weight="600"
                  tone={draft.profile === profile ? 'brand' : 'primary'}
                >
                  {PROFILE_LABEL[profile]}
                </AppText>
              </InteractivePressable>
            ))}
          </View>
        </View>

        <View style={styles.group}>
          <AppText variant="caption" weight="700" tone="secondary">
            Categoría (opcional)
          </AppText>
          <View style={styles.categoryWrap}>
            {categories.map((category) => (
              <InteractivePressable
                key={category.id ? `category:${category.id}` : `suggested:${category.name.trim().toLowerCase()}`}
                accessibilityRole="button"
                accessibilityLabel={category.name}
                accessibilityState={{
                  selected: category.id !== null && draft.category_id === category.id,
                }}
                onPress={() => {
                  if (category.id === null) return;
                  setDirty(true);
                  setDraft((c) => ({
                    ...c,
                    category_id: c.category_id === category.id ? null : category.id,
                  }));
                }}
                haptic="light"
                pressScale={0.98}
                style={[
                  styles.categoryChip,
                  category.id !== null && draft.category_id === category.id && styles.categoryChipSelected,
                ]}
              >
                <AppText variant="caption" weight="600" numberOfLines={2}>
                  {category.name}
                </AppText>
              </InteractivePressable>
            ))}
          </View>
        </View>

        {identifierFields.map((field) => (
          <AppInput
            key={field.key}
            label={field.label}
            value={draft.identifiers[field.key] ?? ''}
            onChangeText={(text) => updateIdentifier(field.key, text)}
            placeholder={field.placeholder}
            accessibilityLabel={field.label}
          />
        ))}
      </ScrollView>

      {confirmDiscard ? (
        <AssetDiscardInline
          onKeepEditing={() => setConfirmDiscard(false)}
          onDiscard={handleDiscard}
        />
      ) : null}
    </AssetFormSheet>
  );
}

function AssetDiscardInline({
  onKeepEditing,
  onDiscard,
}: {
  onKeepEditing: () => void;
  onDiscard: () => void;
}) {
  return (
    <View style={styles.discard}>
      <AppText variant="bodySmall" tone="secondary">
        Tenés cambios sin guardar. Si salís ahora, se pierden.
      </AppText>
      <View style={styles.discardActions}>
        <AppButton
          variant="secondary"
          size="sm"
          title="Seguir editando"
          onPress={onKeepEditing}
        />
        <AppButton variant="danger" size="sm" title="Descartar cambios" onPress={onDiscard} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  footer: { gap: spacing[2] },
  error: { marginBottom: spacing[1] },
  form: { gap: spacing[3], paddingBottom: spacing[6] },
  group: { gap: spacing[2] },
  profileGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  profileChip: {
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[3],
    minHeight: touchTargets.normal,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border.default,
    backgroundColor: colors.surface.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  profileChipSelected: {
    borderColor: colors.brand,
    backgroundColor: colors.brandSoft,
  },
  categoryWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  categoryChip: {
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[2],
    minHeight: touchTargets.normal,
    justifyContent: 'center',
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
    gap: spacing[2],
    paddingTop: spacing[3],
    borderTopWidth: 1,
    borderTopColor: colors.border.subtle,
  },
  discardActions: { flexDirection: 'row', gap: spacing[2] },
});
