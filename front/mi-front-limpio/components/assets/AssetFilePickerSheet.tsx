/**
 * HOMePLUS Assets — S8-04: choose an EXISTING HomeCloud File.
 *
 * The HomeCloud Files screen is NOT duplicated: the picker reads the SAME
 * canonical endpoint (`GET /api/homecloud/files`) with the SAME pagination
 * contract (`limit` / `offset` / `nextOffset`).
 *
 * Contract (frozen):
 *   - SINGLE select only. There is no multi-select and no "attach many".
 *   - The sheet returns ONLY `{ file_id }`: no File payload is cloned into
 *     Assets and nothing about the File is persisted on the Assets side.
 *   - Only ACTIVE Files of the CURRENT household are offered (the endpoint
 *     already filters by household + role=file + lifecycle=active).
 *   - Folder navigation, search (debounced) and pagination are supported.
 *   - No MIME filter.
 *   - A 403 after the sheet is open closes it safely with an honest
 *     permission message; a 5xx shows an ErrorBar inside the picker.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useAppTheme } from '../../context/AppThemeContext';
import { AppButton } from '../ui/AppButton';
import { AppText } from '../ui/AppText';
import { InteractivePressable } from '../ui/InteractivePressable';
import { AssetsSearchField } from './AssetsSearchField';
import { ErrorBar } from './ErrorBar';
import { AssetFormSheet } from './AssetSheet';
import { radius, spacing, touchTargets } from '../../constants/theme';
import { fetchFilesBrowser } from '../../services/homecloud/homecloudFilesService';
import type { HomeCloudFile, HomeCloudFolder } from '../../services/homecloud/homecloudTypes';
import { ApiError } from '../../services/api';

/** The picker page size (frozen: limit 50). */
export const ASSET_FILE_PICKER_PAGE_SIZE = 50;

/** The debounce of the search input (frozen). */
export const ASSET_FILE_PICKER_SEARCH_DEBOUNCE_MS = 250;

type FolderFrame = { id: string | null; name: string };

export function AssetFilePickerSheet({
  visible,
  accessToken,
  onRequestClose,
  onSelected,
}: {
  visible: boolean;
  accessToken: string | null;
  onRequestClose: () => void;
  /** Returns ONLY the file id: the Assets side never clones the File payload. */
  onSelected: (fileId: string) => void;
}) {
  const theme = useAppTheme();

  const [folders, setFolders] = useState<HomeCloudFolder[]>([]);
  const [files, setFiles] = useState<HomeCloudFile[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [folderStack, setFolderStack] = useState<FolderFrame[]>([{ id: null, name: 'Archivos' }]);
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openToken, setOpenToken] = useState(0);

  const requestSeq = useRef(0);
  const currentFolder = folderStack[folderStack.length - 1];

  // Debounce the search input into the query parameter.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(searchInput.trim()), ASSET_FILE_PICKER_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const load = useCallback(
    async (options: { refresh: boolean; offset?: number }) => {
      if (!accessToken) return;
      const sequence = (requestSeq.current += 1);
      const offset = options.offset ?? 0;
      if (offset === 0) setLoading(true);
      else setLoadingMore(true);
      setError(null);
      try {
        const response = await fetchFilesBrowser(accessToken, {
          folderId: currentFolder.id,
          query: query || undefined,
          limit: ASSET_FILE_PICKER_PAGE_SIZE,
          offset,
        });
        if (sequence !== requestSeq.current) return;
        const browser = response.browser;
        setFolders(browser.folders ?? []);
        setFiles((previous) => (offset === 0 ? browser.files ?? [] : [...previous, ...(browser.files ?? [])]));
        setNextOffset(browser.nextOffset ?? null);
        setPermissionDenied(false);
      } catch (caught) {
        if (sequence !== requestSeq.current) return;
        if (caught instanceof ApiError && caught.status === 403) {
          // Fail closed and honestly: the permission is gone.
          setPermissionDenied(true);
          setFiles([]);
          setFolders([]);
          setNextOffset(null);
        } else {
          setError(
            caught && typeof caught === 'object' && 'message' in caught
              ? String((caught as { message: unknown }).message)
              : 'No pudimos buscar los archivos de HomeCloud.',
          );
        }
      } finally {
        if (sequence === requestSeq.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [accessToken, currentFolder.id, query],
  );

  useEffect(() => {
    if (!visible) return;
    setSearchInput('');
    setQuery('');
    setFolderStack([{ id: null, name: 'Archivos' }]);
    setSelectedId(null);
    setPermissionDenied(false);
    setError(null);
    // The token is the trigger of the load: opening the sheet asks for the
    // root folder exactly once (no duplicate request on open).
    setOpenToken((token) => token + 1);
    // load cambia por closure; visible es el disparador real.
  }, [visible]);

  // Reload when the folder or the query changes (after the debounce).
  // `visible` NO es dependencia: si lo fuera, al abrir la hoja se pediría dos
  // veces (una por el cambio de visible y otra por el token de apertura).
  useEffect(() => {
    if (!visible) return;
    void load({ refresh: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openToken, currentFolder.id, query]);

  const selectedFile = useMemo(
    () => files.find((file) => file.id === selectedId) ?? null,
    [files, selectedId],
  );

  if (permissionDenied) {
    return (
      <AssetFormSheet
        visible={visible}
        title="Elegir de HomeCloud"
        onRequestClose={onRequestClose}
        footer={
          <AppButton
            variant="secondary"
            title="Cerrar"
            onPress={onRequestClose}
            accessibilityLabel="Cerrar"
          />
        }
      >
        <AppText variant="body" tone="secondary">
          Necesitás permiso para ver los archivos de HomeCloud.
        </AppText>
      </AssetFormSheet>
    );
  }

  const ctaTitle = selectedFile ? 'Agregar' : 'Elegí un archivo';

  return (
    <AssetFormSheet
      visible={visible}
      title="Elegir de HomeCloud"
      subtitle={currentFolder.name}
      onRequestClose={onRequestClose}
      closeDisabled={loading}
      footer={
        <AppButton
          variant="primary"
          title={ctaTitle}
          disabled={!selectedFile || loading}
          onPress={() => {
            if (!selectedFile) return;
            onSelected(selectedFile.id);
          }}
          accessibilityLabel={selectedFile ? `Agregar ${selectedFile.displayName}` : ctaTitle}
          accessibilityHint={selectedFile ? 'Agrega el archivo elegido a este activo' : undefined}
        />
      }
    >
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.body}>
          <AssetsSearchField
            value={searchInput}
            onChangeText={setSearchInput}
            placeholder="Buscar en HomeCloud"
            accessibilityLabel="Buscar en HomeCloud"
          />

          {folderStack.length > 1 ? (
            <AppButton
              variant="ghost"
              size="sm"
              title="← Volver"
              onPress={() => setFolderStack((stack) => stack.slice(0, -1))}
              accessibilityLabel="Volver a la carpeta anterior"
            />
          ) : null}

          <ErrorBar
            visible={error !== null}
            message={error ?? ''}
            action={{ label: 'Reintentar', onPress: () => void load({ refresh: true }) }}
          />

          {folders.length > 0 ? (
            <View style={styles.list}>
              {folders.map((folder) => (
                <InteractivePressable
                  key={folder.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Abrir carpeta ${folder.name}`}
                  accessibilityHint="Muestra los archivos de la carpeta"
                  onPress={() =>
                    setFolderStack((stack) => [...stack, { id: folder.id, name: folder.name }])
                  }
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
                  <AppText variant="body" weight="600" style={{ color: theme.colors.text.primary }}>
                    {folder.name}
                  </AppText>
                </InteractivePressable>
              ))}
            </View>
          ) : null}

          {loading && files.length === 0 ? (
            <AppText variant="bodySmall" tone="tertiary">
              Buscando archivos…
            </AppText>
          ) : files.length === 0 && !loading ? (
            <AppText variant="bodySmall" tone="secondary">
              No hay archivos para mostrar.
            </AppText>
          ) : (
            <View style={styles.list}>
              {files.map((file) => (
                <InteractivePressable
                  key={file.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Elegir ${file.displayName}`}
                  accessibilityState={{ selected: selectedId === file.id }}
                  onPress={() => setSelectedId(file.id)}
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
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <AppText
                      variant="bodySmall"
                      weight="600"
                      numberOfLines={2}
                      style={{ color: theme.colors.text.primary }}
                    >
                      {file.displayName}
                    </AppText>
                    <AppText
                      variant="caption"
                      tone="secondary"
                      numberOfLines={1}
                      style={{ color: theme.colors.text.secondary }}
                    >
                      {file.extension ? file.extension.toUpperCase() : 'Archivo'}
                    </AppText>
                  </View>
                </InteractivePressable>
              ))}
            </View>
          )}

          {nextOffset !== null ? (
            <AppButton
              variant="secondary"
              size="sm"
              title={loadingMore ? 'Cargando…' : 'Cargar más'}
              loading={loadingMore}
              disabled={loadingMore}
              onPress={() => void load({ refresh: false, offset: nextOffset })}
              accessibilityLabel="Cargar más archivos"
            />
          ) : null}
        </View>
      </ScrollView>
    </AssetFormSheet>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 0,
  },
  scrollContent: {
    paddingBottom: spacing[2],
  },
  body: {
    gap: spacing[3],
  },
  list: {
    gap: spacing[2],
  },
  row: {
    minHeight: touchTargets.senior,
    paddingHorizontal: spacing[4],
    paddingVertical: spacing[3],
    borderRadius: radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
});
