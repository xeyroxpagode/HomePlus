import { requestDraftClose } from '../../utils/requestDraftClose';
import { useMemoryPreviewUrl } from './useMemoryPreviewUrl';
import React, { useEffect, useRef, useState } from 'react';
import { Image, ScrollView, View } from 'react-native';
import { ActionSheet, AppButton, AppInput, AppText } from '../ui';
import { fetchHomeCloudAlbums } from '../../services/homecloud/homecloudReadService';
import { albumIntentId, createMemoryAlbum, updateMemoryAlbum } from '../../services/homecloud/homecloudAlbums';
import type { HomeCloudAlbum } from '../../services/homecloud/homecloudTypes';

export function MemoryAlbumsBar({ token, selectedId, onSelect, canOrganize, revision, covers = [] }: {
  token: string; selectedId: string | null; onSelect: (id: string | null) => void; canOrganize: boolean; revision: number; covers?: { albumId: string; contentId: string }[];
}) {
  const [albums, setAlbums] = useState<HomeCloudAlbum[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<HomeCloudAlbum | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmTrash, setConfirmTrash] = useState(false);
  const [version, setVersion] = useState(0);
  const intent = useRef<string | null>(null);
  const flight = useRef(false);
  useEffect(() => {
    let current = true;
    void fetchHomeCloudAlbums(token).then(items => { if (current) { setAlbums(items); setError(null); } }).catch(() => { if (current) setError('No pudimos cargar los álbumes.'); });
    return () => { current = false; };
  }, [token, revision, version]);
  const save = async (trash = false) => {
    if (flight.current || !canOrganize || (!trash && !name.trim())) return;
    flight.current = true; setBusy(true); setError(null);
    try {
      if (editing) await updateMemoryAlbum(token, editing.id, trash ? undefined : name.trim());
      else { intent.current ??= albumIntentId(); await createMemoryAlbum(token, intent.current, name.trim()); }
      if (trash && selectedId === editing?.id) onSelect(null);
      setOpen(false); setVersion(value => value + 1);
    } catch { setError('No pudimos guardar el álbum. Podés reintentar.'); }
    finally { flight.current = false; setBusy(false); }
  };
  const begin = (album: HomeCloudAlbum | null) => { setEditing(album); setName(album?.name ?? ''); intent.current = null; setConfirmTrash(false); setError(null); setOpen(true); };
  return <View style={{ paddingHorizontal: 20, gap: 8 }}>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: 8 }}>
      <AppButton title="Todas las fotos" size="sm" variant={selectedId === null ? 'primary' : 'secondary'} onPress={() => onSelect(null)} />
      {albums.map(album => <AppButton key={album.id} leftSlot={covers.some(cover => cover.albumId === album.id) ? <AlbumCover token={token} contentId={covers.find(cover => cover.albumId === album.id)?.contentId} /> : undefined} title={album.name} size="sm" variant={selectedId === album.id ? 'primary' : 'secondary'} accessibilityState={{ selected: selectedId === album.id }} onPress={() => onSelect(album.id)} />)}
      {canOrganize ? <AppButton title="Crear álbum" variant="ghost" size="sm" onPress={() => begin(null)} /> : null}
    </ScrollView>
    {selectedId && canOrganize ? <AppButton title="Administrar álbum" size="sm" variant="ghost" onPress={() => begin(albums.find(album => album.id === selectedId) ?? null)} /> : null}
    {error && !open ? <AppButton title="Reintentar álbumes" variant="ghost" onPress={() => setVersion(value => value + 1)} /> : null}
    <ActionSheet visible={open} title={editing ? 'Editar álbum' : 'Crear álbum'} size="content" onRequestClose={() => requestDraftClose(name !== (editing?.name ?? ''), () => setOpen(false))} closeDisabled={busy}
      footer={<AppButton title="Guardar álbum" disabled={busy || !name.trim() || confirmTrash} loading={busy} onPress={() => void save()} />}>
      <View style={{ gap: 12 }}>
        <AppInput label="Nombre del álbum" value={name} maxLength={120} editable={!busy} onChangeText={value => { setName(value); intent.current = null; }} />
        {error ? <AppText tone="danger">{error}</AppText> : null}
        {editing ? confirmTrash ? <>
          <AppText>¿Eliminar este álbum? Las fotos se conservan en la galería y en sus otros álbumes.</AppText>
          <AppButton title="Conservar álbum" variant="secondary" disabled={busy} onPress={() => setConfirmTrash(false)} />
          <AppButton title="Eliminar álbum y conservar fotos" variant="danger" disabled={busy} onPress={() => void save(true)} />
        </> : <AppButton title="Eliminar álbum" variant="ghost" onPress={() => setConfirmTrash(true)} /> : null}
      </View>
    </ActionSheet>
  </View>;
}

function AlbumCover({ token, contentId }: { token: string; contentId?: string }) {
  const preview = useMemoryPreviewUrl(token, contentId ?? '', Boolean(contentId));
  return preview.phase === 'ready' ? <Image source={{ uri: preview.url }} style={{ width: 32, height: 32, borderRadius: 8 }} accessibilityIgnoresInvertColors /> : null;
}
