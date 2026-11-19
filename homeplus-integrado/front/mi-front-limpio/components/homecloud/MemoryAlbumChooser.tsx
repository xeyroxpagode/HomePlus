import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { AppButton, AppInput, AppText } from '../ui';
import { fetchHomeCloudAlbums } from '../../services/homecloud/homecloudReadService';
import { albumIntentId, createMemoryAlbum } from '../../services/homecloud/homecloudAlbums';
import type { HomeCloudAlbum } from '../../services/homecloud/homecloudTypes';

/** Same compact selector in upload preview and viewer. No nested native Modal. */
export function MemoryAlbumChooser({ token, selectedIds, onSelect, canCreate, multiple = false, disabled = false, onBusyChange }: {
  token: string; selectedIds: readonly string[]; onSelect: (id: string | null) => void;
  canCreate: boolean; multiple?: boolean; disabled?: boolean; onBusyChange?: (busy: boolean) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [albums, setAlbums] = useState<HomeCloudAlbum[]>([]);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intent = useRef<string | null>(null);
  const submitting = useRef(false);
  useEffect(() => {
    let current = true;
    setLoading(true);
    void fetchHomeCloudAlbums(token).then(items => { if (current) { setAlbums(items); setError(null); } }).catch(() => { if (current) setError('No pudimos cargar los álbumes. Volvé a abrir el selector.'); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [token, open]);
  const create = async () => {
    if (submitting.current || !name.trim() || !canCreate || disabled) return;
    submitting.current = true; setBusy(true); onBusyChange?.(true); setError(null);
    intent.current ??= albumIntentId();
    try {
      const album = await createMemoryAlbum(token, intent.current, name.trim());
      setAlbums(previous => [...previous.filter(item => item.id !== album.id), album]);
      intent.current = null; setName(''); setCreating(false); onSelect(album.id); setOpen(false);
    } catch { setError('No pudimos crear el álbum. La foto sigue seleccionada; podés reintentar.'); }
    finally { submitting.current = false; setBusy(false); onBusyChange?.(false); }
  };
  const names = albums.filter(album => selectedIds.includes(album.id)).map(album => album.name).join(', ');
  return <View style={{ gap: 8 }}>
    <AppButton title={`Álbum: ${loading ? 'Cargando…' : error ? 'No disponible' : names || 'Sin álbum'}`} variant="secondary" disabled={disabled || busy} onPress={() => setOpen(value => !value)} accessibilityLabel="Elegir álbum de la foto" />
    {open ? <View style={{ gap: 8 }}>
      {error ? <AppText tone="danger" variant="caption">{error}</AppText> : null}
      <ScrollView style={{ maxHeight: 160 }} keyboardShouldPersistTaps="handled">
        {!multiple ? <AppButton title="Sin álbum" variant="ghost" disabled={disabled || busy} onPress={() => { onSelect(null); setOpen(false); }} /> : null}
        {albums.map(album => <AppButton key={album.id} title={album.name} variant={selectedIds.includes(album.id) ? 'primary' : 'ghost'} accessibilityState={{ selected: selectedIds.includes(album.id) }} disabled={disabled || busy} onPress={() => { onSelect(album.id); if (!multiple) setOpen(false); }} />)}
      </ScrollView>
      {canCreate ? creating ? <>
        <AppInput label="Nombre del álbum" value={name} maxLength={120} onChangeText={value => { setName(value); intent.current = null; }} editable={!busy} returnKeyType="done" onSubmitEditing={() => void create()} />
        <AppButton title="Crear álbum y seleccionar" loading={busy} disabled={busy || !name.trim()} onPress={() => void create()} />
        <AppButton title="Cancelar nombre" variant="ghost" disabled={busy} onPress={() => setCreating(false)} />
      </> : <AppButton title="Crear álbum" variant="secondary" onPress={() => setCreating(true)} /> : null}
    </View> : null}
  </View>;
}
