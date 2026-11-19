import { KeyboardAwareScrollView } from 'react-native-keyboard-aware-scroll-view';
import { MemoryAlbumChooser } from './MemoryAlbumChooser';
import { setAlbumCover, setPhotoFavorite, setMemoryAlbumMembership } from '../../services/homecloud/homecloudAlbums';
import React, { useEffect, useState } from 'react';
import { Image, View } from 'react-native';
import { ActionSheet } from '../ui/ActionSheet';
import { AppButton, AppText } from '../ui';
import { fetchHomeCloudContentAccess } from '../../services/homecloud/homecloudReadService';
import { requestJson, OPERATION_KINDS } from '../../services/api';
import type { HomeCloudMemoryListItem } from '../../services/homecloud/homecloudTypes';

export function PhotoMemoryViewer({ memory, accessToken, canDelete, canOrganize = false, preferencesAvailable = false, favorite = false, albumId, onChanged, onClose, onDeleted }: {
  memory: HomeCloudMemoryListItem | null; accessToken: string | null; canDelete: boolean; canOrganize?: boolean; preferencesAvailable?: boolean; favorite?: boolean; albumId?: string | null; onChanged?: () => void;
  onClose: () => void; onDeleted: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [albumPending, setAlbumPending] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [albumIds, setAlbumIds] = useState<readonly string[]>([]);
  const [organizing, setOrganizing] = useState(false);
  const organizingRef = React.useRef(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setUrl(null); setError(null); setConfirmDelete(false); setOptionsOpen(false); setAlbumIds(memory?.albumIds ?? []);
    if (!memory || !accessToken) return;
    const controller = new AbortController();
    void fetchHomeCloudContentAccess(accessToken, memory.id, 'original', { signal: controller.signal, ttl: 60 })
      .then(result => { if (!controller.signal.aborted && 'signedUrl' in result) setUrl(result.signedUrl); })
      .catch(() => { if (!controller.signal.aborted) setError('No pudimos abrir la foto. Reintentá.'); });
    return () => controller.abort();
  }, [memory?.id, accessToken, attempt]);
  const remove = async () => {
    if (!memory || !accessToken || deleting || !canDelete) return;
    setDeleting(true); setError(null);
    try {
      await requestJson(`/api/homecloud/memories/${memory.id}/trash`, { method: 'POST', accessToken, operationKind: OPERATION_KINDS.NON_VERSIONED_MUTATION });
      onDeleted();
    } catch { setError('No pudimos eliminar la foto. Podés reintentar.'); }
    finally { setDeleting(false); }
  };
  const toggleAlbum = async (id: string | null) => {
    if (!id || !memory || !accessToken || !canOrganize || organizingRef.current) return;
    organizingRef.current = true; setOrganizing(true); setError(null);
    const included = !albumIds.includes(id);
    try {
      await setMemoryAlbumMembership(accessToken, id, memory.id, included);
      setAlbumIds(previous => included ? [...previous, id] : previous.filter(value => value !== id));
      onChanged?.();
    } catch { setError('No pudimos cambiar el álbum. La foto se conserva.'); }
    finally { organizingRef.current = false; setOrganizing(false); }
  };
  const savePreference = async (cover = false) => {
    if (!memory || !accessToken || organizingRef.current || !preferencesAvailable) return;
    organizingRef.current = true; setOrganizing(true); setError(null);
    try {
      if (cover && albumId && canOrganize) await setAlbumCover(accessToken, albumId, memory.id);
      else if (!cover) await setPhotoFavorite(accessToken, memory.id, !favorite);
      onChanged?.();
    } catch { setError('No pudimos guardar esta opción. Podés reintentar.'); }
    finally { organizingRef.current = false; setOrganizing(false); }
  };
  return <ActionSheet visible={Boolean(memory)} title="Foto" size="near-full" onRequestClose={onClose} closeDisabled={deleting || organizing || albumPending}
    footer={<AppButton title={optionsOpen ? 'Volver a la foto' : 'Opciones de la foto'} variant="secondary" onPress={() => setOptionsOpen(value => !value)} disabled={deleting || organizing || albumPending} />}>
    {optionsOpen && memory ? <KeyboardAwareScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 12, paddingBottom: 16 }} keyboardShouldPersistTaps="handled" enableOnAndroid>
      <AppText variant="caption" tone="secondary">{memory.displayName ?? 'Foto'}{memory.uploadedAt ? ` · Guardada ${new Date(memory.uploadedAt).toLocaleDateString('es-AR')}` : ''}</AppText>
      {canOrganize && accessToken ? <MemoryAlbumChooser onBusyChange={setAlbumPending} token={accessToken} selectedIds={albumIds} multiple canCreate disabled={organizing || deleting} onSelect={id => void toggleAlbum(id)} /> : null}
      <AppText variant="caption" tone="secondary">Una foto puede estar en varios álbumes. Tocá uno seleccionado para quitarla sin borrar la foto.</AppText>
      {preferencesAvailable ? <>
        <AppButton title={favorite ? 'Quitar de favoritos' : 'Marcar como favorita'} variant="secondary" disabled={organizing || albumPending} onPress={() => void savePreference()} />
        {canOrganize && albumId && albumIds.includes(albumId) ? <AppButton title="Usar como portada del álbum" variant="secondary" disabled={organizing || albumPending} onPress={() => void savePreference(true)} /> : null}
      </> : null}
      {canDelete ? confirmDelete ? <>
        <AppText>¿Enviar esta foto a la papelera?</AppText>
        <AppButton title="Cancelar" variant="secondary" disabled={deleting} onPress={() => setConfirmDelete(false)} />
        <AppButton title="Enviar a papelera" variant="danger" loading={deleting} disabled={deleting} onPress={() => void remove()} />
      </> : <AppButton title="Eliminar foto" variant="ghost" onPress={() => setConfirmDelete(true)} /> : null}
      {error ? <AppText tone="danger">{error}</AppText> : null}
    </KeyboardAwareScrollView> : <>

    {error ? <View><AppText tone="danger">{error}</AppText><AppButton title="Reintentar" variant="secondary" onPress={() => setAttempt(value => value + 1)} /></View> : null}
    {url ? <Image source={{ uri: url, cache: 'reload' }} resizeMode="contain" style={{ flex: 1, width: '100%' }} accessibilityLabel="Foto del hogar" onError={() => setError('No pudimos mostrar la foto. Reintentá.')} /> : !error ? <AppText tone="secondary" accessibilityLiveRegion="polite">Abriendo foto…</AppText> : null}
    </>}
  </ActionSheet>;
}
