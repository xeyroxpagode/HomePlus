import { KeyboardAwareScrollView } from 'react-native-keyboard-aware-scroll-view';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import { AppButton, AppText } from '../../components/ui';
import { MemoryAlbumChooser } from '../../components/homecloud/MemoryAlbumChooser';
import { ActionSheet } from '../../components/ui/ActionSheet';
import { HomePlusIcon } from '../../constants/icons';
import { spacing } from '../../constants/theme';
import { useAppTheme } from '../../context/AppThemeContext';
import {
  createPhotoMemoryUploadService,
  type PhotoMemoryConfig,
  type PhotoMemoryState,
} from './homecloudPhotoMemoryService';

export function PhotoMemoryIntake({ config, onComplete }: {
  config: PhotoMemoryConfig;
  onComplete: (contentId: string) => void;
}) {
  const { colors } = useAppTheme();
  const [state, setState] = useState<PhotoMemoryState>({ status: 'idle' });
  const [albumPending, setAlbumPending] = useState(false);
  const [selectedAlbumId, setSelectedAlbumId] = useState<string | null>(config.initialAlbumId ?? null);
  const notifiedContentIds = useRef(new Set<string>());
  const { accessToken, capabilities, householdId, initialAlbumId, intakeSource } = config;
  const liveConfig = useRef(config);
  liveConfig.current = config;
  const service = useMemo(
    () => createPhotoMemoryUploadService({
      accessToken: liveConfig.current.accessToken,
      get capabilities() { return liveConfig.current.capabilities; },
      getAccessToken: () => liveConfig.current.getAccessToken?.() ?? liveConfig.current.accessToken,
      householdId,
      initialAlbumId,
      intakeSource,
    }),
    [householdId, initialAlbumId, intakeSource],
  );

  useEffect(() => {
    const unsubscribe = service.subscribe(setState);
    setSelectedAlbumId(initialAlbumId ?? null);
    setAlbumPending(false);
    void service.recover();
    return unsubscribe;
  }, [service, initialAlbumId]);

  useEffect(() => {
    if (state.status !== 'completed' || !state.contentId || notifiedContentIds.current.has(state.contentId)) return;
    notifiedContentIds.current.add(state.contentId);
    onComplete(state.contentId);
  }, [onComplete, state]);

  const busy = state.status === 'picking' || state.status === 'uploading';
  const addPhoto = async (source: 'gallery' | 'camera' = 'gallery') => {
    await service.pick(source);
  };
  const retry = async () => {
    await service.retry();
  };

  return (
    <View style={styles.root}>
      <View style={styles.actions}>
        <AppButton
          title={state.status === 'picking' ? 'Abriendo galería…' : state.status === 'uploading' ? 'Guardando foto…' : 'Agregar foto'}
          onPress={() => void addPhoto()}
          loading={state.status === 'uploading'}
          disabled={busy || !config.capabilities.contribute}
          accessibilityLabel="Elegir una foto de la galería"
          leftSlot={<HomePlusIcon name="image-outline" size={19} color={colors.text.inverse} />}
          style={styles.addButton}
        />
        <AppButton title="Cámara" variant="secondary" onPress={() => void addPhoto('camera')} disabled={busy || !config.capabilities.contribute} accessibilityLabel="Sacar una foto" />

      </View>

      {state.status === 'completed' ? (
        <AppText variant="caption" tone="success" accessibilityLiveRegion="polite">Foto guardada.</AppText>
      ) : null}
      {state.status === 'failed' ? (
        <View style={styles.error} accessibilityLiveRegion="assertive">
          <AppText variant="caption" tone="danger" style={styles.errorText}>{state.error}</AppText>
          <AppButton title="Reintentar" variant="secondary" size="sm" onPress={() => void retry()} />
        </View>
      ) : null}

      <ActionSheet
        visible={state.status === 'preview' || (state.status === 'uploading' && Boolean(state.artifact))}
        title="Guardar foto"
        subtitle="Se guardará de forma privada en este hogar."
        size="near-full"
        onRequestClose={() => service.discardSelection()}
        closeDisabled={state.status === 'uploading' || albumPending}
        footer={<AppButton title="Guardar foto" loading={state.status === 'uploading'} disabled={state.status === 'uploading' || albumPending} onPress={() => void service.uploadSelected()} accessibilityLabel="Confirmar y guardar foto" />}
      >
        <KeyboardAwareScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: spacing[3], paddingBottom: spacing[3] }} keyboardShouldPersistTaps="handled" enableOnAndroid extraScrollHeight={16}>
          {state.artifact ? <Image source={{ uri: state.artifact.localUri }} resizeMode="contain" style={{ width: '100%', aspectRatio: 1.3 }} accessibilityLabel="Vista previa de la foto seleccionada" /> : null}
          <MemoryAlbumChooser onBusyChange={setAlbumPending} token={accessToken} selectedIds={selectedAlbumId ? [selectedAlbumId] : []} canCreate={Boolean(capabilities.organize)} disabled={state.status === 'uploading'} onSelect={id => { setSelectedAlbumId(id); service.selectAlbum(id); }} />
        </KeyboardAwareScrollView>
      </ActionSheet>


    </View>
  );
}

const styles = StyleSheet.create({
  root: { paddingHorizontal: spacing[5], paddingBottom: spacing[2], gap: spacing[2] },
  actions: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] },
  addButton: { flex: 1 },
  error: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] },
  errorText: { flex: 1 },
  albumList: { gap: spacing[2] },
});
