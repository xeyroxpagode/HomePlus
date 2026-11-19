import { useAppTheme } from '../../context/AppThemeContext';
import { productNames } from '../../constants/productLanguage';
import React, { useCallback, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import {
  useAssetsCapabilities,
  useAssetsList,
  useDebouncedValue,
} from '../../hooks/assets/useAssetsData';
import { assetsCache } from '../../services/assets/assetsCache';
import { assetsKeys } from '../../services/assets/assetsKeys';
import { canPerform } from '../../services/assets';
import { AppScreen } from '../../components/ui/AppScreen';
import { AppText } from '../../components/ui/AppText';
import { AppPageHeader } from '../../components/ui/AppPageHeader';
import { IconButton } from '../../components/ui/IconButton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { Skeleton } from '../../components/ui/Skeleton';
import { AssetRow } from '../../components/assets/AssetRow';
import { AssetsSearchField } from '../../components/assets/AssetsSearchField';
import { AssetsFilterRail } from '../../components/assets/AssetsFilterRail';
import { AssetCreateSheet } from '../../components/assets/AssetCreateSheet';
import { AssetActionMenu, type AssetMenuOption } from '../../components/assets/AssetSheet';
import { ErrorBar } from '../../components/assets/ErrorBar';
import { navigationGeometry, spacing } from '../../constants/theme';
import type { AssetProfileFilterKey } from '../../services/assets';

export type AssetsListScreenProps = {
  scope: 'normal' | 'archived' | 'trash';
  title: string;
  /** Root muestra subtítulo, búsqueda, filtros y accesos secundarios. */
  isRoot?: boolean;
};

const SKELETON_ROWS = 6;

function AssetsSkeleton() {
  return (
    <View testID="assets.loading" style={{ padding: spacing[5], gap: spacing[2] }}>
      {[...Array(SKELETON_ROWS)].map((_, i) => (
        <Skeleton key={i} style={styles.skeletonRow} />
      ))}
    </View>
  );
}

export function AssetsListScreen({ scope, title, isRoot = false }: AssetsListScreenProps) {
  const { colors } = useAppTheme();

  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  const navigation = useNavigation<any>();

  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? null;

  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebouncedValue(searchQuery, 200);
  const [filter, setFilter] = useState<AssetProfileFilterKey>('ALL');
  const [createSheet, setCreateSheet] = useState(false);
  const [libraryMenu, setLibraryMenu] = useState(false);

  const { assets, loading, loadingMore, refreshing, error, nextOffset, reload, loadMore } =
    useAssetsList(accessToken, householdId, scope, {
      profile: filter === 'ALL' ? undefined : filter,
      q: debouncedQuery || undefined,
    });

  // El backend es la autoridad; la proyección sólo decide qué se muestra.
  const { capabilities } = useAssetsCapabilities(accessToken, householdId);
  const canCreate = canPerform(capabilities, 'assets.create');

  const handleRowPress = useCallback(
    (assetId: string) => {
      const snapshot = assets.find((item) => item.id === assetId);
      if (householdId && snapshot) assetsCache.set(assetsKeys.detail({ householdId }, assetId), snapshot);
      navigation.navigate('AssetsDetail', { assetId });
    },
    [navigation, assets, householdId],
  );

  const onEndReached = useCallback(() => {
    if (!loadingMore && nextOffset !== null) loadMore();
  }, [loadingMore, nextOffset, loadMore]);

  const isInitialLoading = loading && assets.length === 0;
  // Una búsqueda o un filtro sin resultados NO es "no hay activos": el
  // estado vacío honesto dice que no hay coincidencias (y no ofrece un CTA
  // de creación que no corresponde).
  const hasActiveFilter = debouncedQuery.trim().length > 0 || filter !== 'ALL';
  const clearSearchAndFilters = () => {
    setSearchQuery('');
    setFilter('ALL');
  };

  const emptyState = hasActiveFilter ? (
    <EmptyState
      title="Sin resultados"
      description={
        filter !== 'ALL' && debouncedQuery.trim().length > 0
          ? "No hay objetos que coincidan con esa búsqueda y ese filtro."
          : filter !== 'ALL'
            ? "No hay objetos de ese tipo."
            : "No hay objetos que coincidan con esa búsqueda."
      }
      secondaryActionLabel="Limpiar búsqueda y filtros"
      onSecondaryAction={clearSearchAndFilters}
    />
  ) : isRoot ? (
    <EmptyState
      title="Todavía no agregaste nada"
      description={
        canCreate
          ? 'Registrá objetos, vehículos, mascotas o propiedades para encontrarlos rápido.'
          : "Cuando alguien de tu hogar agregue un objeto, lo vas a ver acá."
      }
      actionLabel={canCreate ? "Agregar un objeto" : undefined}
      onAction={canCreate ? () => setCreateSheet(true) : undefined}
    />
  ) : scope === 'archived' ? (
    <EmptyState
      title="No hay objetos archivados"
      description="Cuando archives un objeto, va a quedar acá con toda su información."
    />
  ) : (
    <EmptyState
      title="Papelera vacía"
      description="Los objetos que mandes a la papelera quedan acá y se pueden recuperar."
    />
  );

  const showHeaderCreate = isRoot && canCreate && (assets.length > 0 || hasActiveFilter);
  const libraryOptions: AssetMenuOption[] = [
    {
      key: 'archived',
      label: 'Archivados',
      description: "Objetos que ya no usás habitualmente",
      icon: 'archive-outline',
      onSelect: () => navigation.navigate('AssetsArchived'),
    },
    {
      key: 'trash',
      label: 'Papelera',
      description: "Objetos que podés recuperar",
      icon: 'trash-outline',
      onSelect: () => navigation.navigate('AssetsTrash'),
    },
  ];

  const goBack = () => {
    if (navigation.canGoBack?.()) navigation.goBack();
    else navigation.navigate('Assets');
  };

  const header = (
    <View>
      <View style={styles.headerBlock}>
        <AppPageHeader
          title={title}
          subtitle={isRoot ? 'Encontrá lo importante de tu hogar' : undefined}
          leading={
            navigation.canGoBack() ? (
              <IconButton
                icon="chevron-back-outline"
                accessibilityLabel={isRoot ? "Volver a Más" : "Volver a Objetos"}
                onPress={goBack}
                variant="plain"
                haptic="none"
              />
            ) : undefined
          }
          action={
            isRoot ? (
              <View style={styles.headerActions}>
                {showHeaderCreate ? (
                  <IconButton
                    icon="add"
                    accessibilityLabel="Agregar un objeto"
                    onPress={() => setCreateSheet(true)}
                    variant="brandSoft"
                    haptic="none"
                  />
                ) : null}
                <IconButton
                  icon="ellipsis-horizontal"
                  accessibilityLabel="Más opciones de Objetos"
                  onPress={() => setLibraryMenu(true)}
                  variant="plain"
                  haptic="none"
                />
              </View>
            ) : undefined
          }
        />
      </View>

      {error && assets.length > 0 ? (
        <View style={{ paddingHorizontal: spacing[5], paddingTop: spacing[2] }}>
          <ErrorBar
            visible
            message="No pudimos actualizar tus objetos."
            action={{ label: 'Reintentar', onPress: reload }}
          />
        </View>
      ) : null}

      {isRoot ? (
        <View style={{ paddingHorizontal: spacing[5], gap: spacing[3] }}>
          <AssetsSearchField
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Buscar por nombre"
          />
          <AssetsFilterRail selected={filter} onSelect={setFilter} />
        </View>
      ) : null}
    </View>
  );

  return (
    <AppScreen padded={false} scroll={false} bottomInset="none">
      {isInitialLoading ? (
        <View style={{ flex: 1 }}>
          {header}
          <AssetsSkeleton />
        </View>
      ) : error && assets.length === 0 ? (
        <View style={{ flex: 1 }}>
          {header}
          <View style={{ paddingHorizontal: spacing[5] }}>
            <ErrorState title="No pudimos cargar tus objetos" description={error} onRetry={reload} />
          </View>
        </View>
      ) : (
        <FlatList
          data={assets}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <View style={styles.rowInset}>
              <AssetRow asset={item} onPress={() => handleRowPress(item.id)} />
            </View>
          )}
          ListHeaderComponent={header}
          ListEmptyComponent={<View style={{ paddingHorizontal: spacing[5] }}>{emptyState}</View>}
          onEndReached={onEndReached}
          onEndReachedThreshold={0.4}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={reload} tintColor={colors.brand} />
          }
          contentContainerStyle={{
            paddingBottom:
              navigationGeometry.bottomBarHeight +
              navigationGeometry.bottomBarBreathingSpace +
              spacing[6],
          }}
          ItemSeparatorComponent={() => <View style={{ height: 0 }} />}
          ListFooterComponent={
            loadingMore ? (
              <View style={styles.footerLoading}>
                <AppText variant="caption" tone="tertiary">
                  Cargando más…
                </AppText>
              </View>
            ) : undefined
          }
        />
      )}

      <AssetCreateSheet
        visible={createSheet}
        onRequestClose={() => setCreateSheet(false)}
        onCreated={(assetId) => {
          setCreateSheet(false);
          reload();
          navigation.navigate('AssetsDetail', { assetId });
        }}
      />
      <AssetActionMenu
        visible={libraryMenu}
        title="Más opciones"
        subtitle={productNames.assets}
        options={libraryOptions}
        onRequestClose={() => setLibraryMenu(false)}
      />
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  headerBlock: { paddingHorizontal: spacing[5], paddingTop: 0, paddingBottom: spacing[3] },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: spacing[1] },
  rowInset: { paddingHorizontal: spacing[5] },
  skeletonRow: { minHeight: 64, borderRadius: 12 },
  footerLoading: { paddingVertical: spacing[4], alignItems: 'center' },
});

/** O01 Root — encontrar un activo. */
export function AssetsRootScreen() {
  return <AssetsListScreen scope="normal" title={productNames.assets} isRoot />;
}

/** Archivados — pantalla secundaria con estados propios. */
export function AssetsArchivedScreen() {
  return <AssetsListScreen scope="archived" title="Archivados" />;
}

/** Papelera — recuperable, sin borrado físico. */
export function AssetsTrashScreen() {
  return <AssetsListScreen scope="trash" title="Papelera" />;
}
