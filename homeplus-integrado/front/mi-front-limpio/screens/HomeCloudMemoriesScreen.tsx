import { readPhotoPreferences, type PhotoPreferences } from '../services/homecloud/homecloudAlbums';
import { MemoryAlbumsBar } from '../components/homecloud/MemoryAlbumsBar';
import { useAppTheme } from '../context/AppThemeContext';
import { useThemeStyles } from '../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../constants/theme';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshControl, SectionList, StyleSheet, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { useHousehold } from '../context/HouseholdContext';
import { AppButton, AppText, EmptyState, ErrorState, Skeleton } from '../components/ui';
import { MemoryCard } from '../components/homecloud/MemoryCards';
import { HomePlusIcon } from '../constants/icons';
import { radius, spacing } from '../constants/theme';
import { listMemories } from '../services/homecloud/homecloudReadService';
import { clearMemoryPreviewCache } from '../services/homecloud/homecloudMemoryPreview';
import { PhotoMemoryViewer } from '../components/homecloud/PhotoMemoryViewer';
import { PhotoMemoryIntake } from '../services/homecloud/PhotoMemoryIntake';
import { evaluateHomeCloudCapabilities } from '../services/homecloud/homecloudCapabilitiesAdapter';
import { fetchHomeCloudCapabilities } from '../services/homecloudCapabilities';
import type { HomeCloudMemoryListItem } from '../services/homecloud/homecloudTypes';
import {
  flattenTimelineForSectionList,
  groupMemoriesForTimeline,
  type TimelineListSection,
} from '../services/homecloud/homecloudMemoriesTimeline';

const MEMORIES_PAGE_SIZE = 50;
const TIMELINE_COLUMNS = 3;

/**
 * HomeCloud STAGE 4B.2 — Memories Root (productive Timeline surface).
 *
 * Authority: Stage 4B.1 read model (`listMemories`: role=memory,
 * lifecycle=active, canonical Timeline order, stable pagination).
 *
 * - Real backend data only: no fixtures, no mocks, no local arrays.
 * - States: loading (skeletons) / empty / error+retry / success / refresh
 *   (pull-to-refresh, same pattern as the rest of the app). No polling.
 * - Grouping uses the semantic date only (never uploadedAt). Unknown dates
 *   render last as "Sin fecha" per the productive backend contract.
 * - Photos open a private V1 viewer; other historical media remain read-only.
 * - Create is photo-only: picker/camera -> preview -> confirmation -> private upload.
 *   Historical video/audio/written memories remain readable.
 */
export function HomeCloudMemoriesView({ active = true }: { active?: boolean }) {
  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  return <ScopedMemoriesView key={`${session?.user.id ?? '-'}:${currentHousehold?.id ?? '-'}`} active={active} />;
}

function ScopedMemoriesView({ active }: { active: boolean }) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  const token = session?.access_token ?? null;

  const [albumId, setAlbumId] = useState<string | null>(null);
  const [photoPreferences, setPhotoPreferences] = useState<PhotoPreferences>({ available: false });
  const [albumRevision, setAlbumRevision] = useState(0);
  const [memories, setMemories] = useState<HomeCloudMemoryListItem[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState({ view: false, contribute: false, organize: false, delete: false, anyWrite: false });
  const hasFocusedOnceRef = useRef(false);
  const requestSeq = useRef(0);
  const loadedRef = useRef(false);
  const [selectedMemory, setSelectedMemory] = useState<HomeCloudMemoryListItem | null>(null);
  useEffect(() => () => { requestSeq.current += 1; clearMemoryPreviewCache(); }, []);

  const previewRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (previewRefreshTimer.current) clearTimeout(previewRefreshTimer.current); }, []);
  useEffect(() => {
    if (!active || !token) return;
    let current = true;
    void fetchHomeCloudCapabilities(token)
      .then(projection => { if (current) setCapabilities(evaluateHomeCloudCapabilities(projection)); })
      .catch(() => { if (current) setCapabilities(evaluateHomeCloudCapabilities(null)); });
    return () => { current = false; };
  }, [active, token]);

  useEffect(() => {
    if (!active || !token) return;
    let current = true;
    void readPhotoPreferences(token).then(value => { if (current) setPhotoPreferences(value); }).catch(() => { if (current) setPhotoPreferences({ available: false }); });
    return () => { current = false; };
  }, [active, token, albumRevision]);

  const loadFirstPage = useCallback(async () => {
    if (!token || !currentHousehold?.id) {
      setLoading(false);
      return;
    }
    const sequence = ++requestSeq.current;
    setLoading(!loadedRef.current);
    setError(null);
    try {
      const page = await listMemories(token, { limit: MEMORIES_PAGE_SIZE, albumId: albumId ?? undefined });
      if (sequence !== requestSeq.current) return;
      loadedRef.current = true;
      setMemories([...page.memories]);
      setNextOffset(page.nextOffset);
    } catch (e) {
      if (sequence === requestSeq.current) setError(e instanceof Error ? e.message : 'No pudimos cargar tus recuerdos.');
    } finally {
      if (sequence === requestSeq.current) setLoading(false);
    }
  }, [token, currentHousehold?.id, albumId]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try { await loadFirstPage(); } finally { setRefreshing(false); }
  }, [loadFirstPage]);

  const loadMore = useCallback(async () => {
    if (!token || !currentHousehold?.id || nextOffset === null || loadingMore || loading) return;
    const sequence = requestSeq.current;
    setLoadingMore(true);
    try {
      const page = await listMemories(token, { limit: MEMORIES_PAGE_SIZE, offset: nextOffset, albumId: albumId ?? undefined });
      if (sequence !== requestSeq.current) return;
      setMemories((previous) => {
        const known = new Set(previous.map((memory) => memory.id));
        return [...previous, ...page.memories.filter((memory) => !known.has(memory.id))];
      });
      setNextOffset(page.nextOffset);
    } catch {
      if (sequence === requestSeq.current) setError('No pudimos cargar más recuerdos. Reintentá con Mostrar más.');
      // Pagination failure is non-fatal: the loaded Timeline stays and the
      // footer button remains available for another attempt.
    } finally {
      setLoadingMore(false);
    }
  }, [token, currentHousehold?.id, nextOffset, loadingMore, loading, albumId]);

  useEffect(() => {
    if (active && !loadedRef.current) void loadFirstPage();
  }, [active, loadFirstPage]);

  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useFocusEffect(
    useCallback(() => {
      if (!active) return;
      if (hasFocusedOnceRef.current) void refreshRef.current();
      hasFocusedOnceRef.current = true;
    }, [active]),
  );

  useEffect(() => {
    setMemories([]);
    setNextOffset(null);
    setError(null);
  }, [currentHousehold?.id]);

  const sections = useMemo<TimelineListSection[]>(
    () => flattenTimelineForSectionList(groupMemoriesForTimeline(memories), TIMELINE_COLUMNS),
    [memories],
  );

  return (
    <View style={styles.screen}>
      <View style={styles.titleRow}>
        <AppText variant="title3" weight="800" style={styles.headerTitle}>
          {'Recuerdos'}
        </AppText>
        <AppButton variant="icon" size="sm" onPress={() => void refresh()} accessibilityLabel="Actualizar recuerdos">
          <HomePlusIcon name="refresh" size={21} color={colors.text.secondary} />
        </AppButton>
      </View>
      {token && currentHousehold ? (
        <PhotoMemoryIntake
          config={{
            householdId: currentHousehold.id,
            accessToken: token,
            capabilities,
            initialAlbumId: albumId,
          }}
          onComplete={() => {
            setAlbumRevision(value => value + 1);
            void refresh();
            if (previewRefreshTimer.current) clearTimeout(previewRefreshTimer.current);
            // One bounded revalidation lets the asynchronous server thumbnail
            // appear without polling or downloading originals for grid cells.
            previewRefreshTimer.current = setTimeout(() => void refresh(), 2000);
          }}
        />
      ) : null}
      {token ? <MemoryAlbumsBar covers={photoPreferences.covers ?? []} token={token} selectedId={albumId} canOrganize={capabilities.organize} revision={albumRevision} onSelect={id => { if (id === albumId) return; requestSeq.current += 1; loadedRef.current = false; setMemories([]); setNextOffset(null); setLoading(true); setAlbumId(id); }} /> : null}
      <PhotoMemoryViewer preferencesAvailable={photoPreferences.available} favorite={photoPreferences.favoriteIds?.includes(selectedMemory?.id ?? '') ?? false} albumId={albumId} memory={selectedMemory} accessToken={token} canDelete={capabilities.delete} canOrganize={capabilities.organize} onChanged={() => { setAlbumRevision(value => value + 1); void refresh(); }} onClose={() => setSelectedMemory(null)} onDeleted={() => { setSelectedMemory(null); void refresh(); }} />
      {error && memories.length > 0 ? <AppText variant="bodySmall" tone="danger" style={{ paddingHorizontal: spacing[5] }}>{error}</AppText> : null}
      {refreshing ? <AppText variant="caption" tone="secondary" accessibilityLiveRegion="polite" style={{ paddingHorizontal: spacing[5] }}>Actualizando…</AppText> : null}
      {loading ? (
        <MemoriesLoadingSkeleton />
      ) : error && memories.length === 0 ? (
        <View style={styles.center}>
          <ErrorState
            title="No pudimos cargar tus recuerdos"
            description={error}
            retryLabel="Reintentar"
            onRetry={() => void loadFirstPage()}
          />
        </View>
      ) : memories.length === 0 ? (
        <View style={{ paddingHorizontal: spacing[5] }}>
          <EmptyState variant="compact" title="Todavía no hay fotos" description="Elegí una foto o usá la cámara para guardar un recuerdo privado del hogar." />
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(row) => row.key}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refresh()} />}
          renderSectionHeader={({ section }) => (
            <View style={styles.sectionHeader}>
              {section.yearTitle && section.yearTitle !== section.title ? (
                <AppText variant="title3" weight="800">
                  {section.yearTitle}
                </AppText>
              ) : null}
              <AppText variant="bodySmall" tone="secondary" weight="600">
                {section.yearTitle && section.yearTitle !== section.title ? section.title : section.yearTitle ?? section.title}
              </AppText>
            </View>
          )}
          renderItem={({ item }) => (
            <View style={styles.row}>
              {item.items.map((memory) => (
                <MemoryCard key={memory.id} memory={memory} accessToken={token} onPress={memory.kind === 'image' ? () => setSelectedMemory(memory) : undefined} />
              ))}
              {Array.from({ length: TIMELINE_COLUMNS - item.items.length }).map((_, index) => (
                <View key={`spacer-${index}`} style={styles.rowSpacer} />
              ))}
            </View>
          )}
          ListFooterComponent={
            nextOffset !== null ? (
              <View style={styles.footer}>
                <AppButton
                  title={loadingMore ? 'Cargando…' : 'Mostrar más recuerdos'}
                  variant="secondary"
                  disabled={loadingMore}
                  onPress={() => void loadMore()}
                />
              </View>
            ) : undefined
          }
        />
      )}
    </View>
  );
}

function MemoriesLoadingSkeleton() {
  const styles = useThemeStyles(createStylesForTheme);

  return (
    <View style={styles.list}>
      <Skeleton variant="line" width="32%" height={22} />
      <View style={styles.skeletonRow}>
        <Skeleton variant="card" height={128} style={styles.skeletonTile} />
        <Skeleton variant="card" height={128} style={styles.skeletonTile} />
        <Skeleton variant="card" height={128} style={styles.skeletonTile} />
      </View>
      <Skeleton variant="line" width="44%" height={22} />
      <View style={styles.skeletonRow}>
        <Skeleton variant="card" height={128} style={styles.skeletonTile} />
        <Skeleton variant="card" height={128} style={styles.skeletonTile} />
        <Skeleton variant="card" height={128} style={styles.skeletonTile} />
      </View>
    </View>
  );
}



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background.base },
  headerTitle: { flex: 1 },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing[5],
    paddingVertical: spacing[4],
  },
  list: { paddingHorizontal: spacing[5], paddingBottom: spacing[8] },
  sectionHeader: { paddingTop: spacing[3], paddingBottom: spacing[2], gap: 2 },
  row: { flexDirection: 'row', gap: spacing[2], marginBottom: spacing[3] },
  rowSpacer: { flex: 1 },
  footer: { paddingVertical: spacing[4], alignItems: 'center' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing[8], gap: spacing[3] },
  skeletonRow: { flexDirection: 'row', gap: spacing[2], marginVertical: spacing[2] },
  skeletonTile: { flex: 1, borderRadius: radius.lg },
});
}
