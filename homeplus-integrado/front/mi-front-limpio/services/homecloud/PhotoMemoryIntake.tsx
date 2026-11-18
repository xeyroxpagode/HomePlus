import React, { useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppButton, AppText } from '../../components/ui';
import { ActionSheet } from '../../components/ui/ActionSheet';
import { HomePlusIcon } from '../../constants/icons';
import { colors, spacing } from '../../constants/theme';
import {
  createPhotoMemoryUploadService,
  type PhotoMemoryAlbum,
  type PhotoMemoryConfig,
  type PhotoMemoryState,
} from './homecloudPhotoMemoryService';

export function PhotoMemoryIntake({ config, onComplete }: {
  config: PhotoMemoryConfig;
  onComplete: (contentId: string) => void;
}) {
  const [state, setState] = useState<PhotoMemoryState>({ status: 'idle' });
  const [albums, setAlbums] = useState<PhotoMemoryAlbum[]>([{ id: null, name: 'Recuerdos' }]);
  const [selectedAlbumId, setSelectedAlbumId] = useState<string | null>(config.initialAlbumId ?? null);
  const [albumSheetOpen, setAlbumSheetOpen] = useState(false);
  const notifiedContentIds = useRef(new Set<string>());
  const { accessToken, capabilities, getAccessToken, householdId, initialAlbumId, intakeSource } = config;
  const service = useMemo(
    () => createPhotoMemoryUploadService({
      accessToken,
      capabilities,
      getAccessToken,
      householdId,
      initialAlbumId,
      intakeSource,
    }),
    [accessToken, capabilities, getAccessToken, householdId, initialAlbumId, intakeSource],
  );

  useEffect(() => {
    const unsubscribe = service.subscribe(setState);
    void service.loadAlbums().then(setAlbums);
    void service.recover();
    return unsubscribe;
  }, [service]);

  useEffect(() => {
    if (state.status !== 'completed' || !state.contentId || notifiedContentIds.current.has(state.contentId)) return;
    notifiedContentIds.current.add(state.contentId);
    onComplete(state.contentId);
  }, [onComplete, state]);

  const selectedAlbum = albums.find((album) => album.id === selectedAlbumId) ?? albums[0];
  const busy = state.status === 'picking' || state.status === 'uploading';
  const addPhoto = async () => {
    await service.pickAndUpload();
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
          disabled={busy || !config.capabilities.contribute}
          accessibilityLabel="Elegir una foto de la galería"
          leftSlot={<HomePlusIcon name="image-outline" size={19} color={colors.text.inverse} />}
          style={styles.addButton}
        />
        {albums.length > 1 ? (
          <AppButton
            title={selectedAlbum?.name ?? 'Recuerdos'}
            variant="secondary"
            size="sm"
            onPress={() => setAlbumSheetOpen(true)}
            disabled={busy}
            accessibilityLabel={`Guardar en ${selectedAlbum?.name ?? 'Recuerdos'}`}
          />
        ) : null}
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
        visible={albumSheetOpen}
        title="Guardar en"
        subtitle="Elegí un álbum o dejala en Recuerdos."
        size="content"
        onRequestClose={() => setAlbumSheetOpen(false)}
      >
        <View style={styles.albumList}>
          {albums.map((album) => (
            <AppButton
              key={album.id ?? 'root'}
              title={album.name}
              variant={album.id === selectedAlbumId ? 'primary' : 'secondary'}
              onPress={() => {
                setSelectedAlbumId(album.id);
                service.selectAlbum(album.id);
                setAlbumSheetOpen(false);
              }}
              accessibilityState={{ selected: album.id === selectedAlbumId }}
            />
          ))}
        </View>
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
