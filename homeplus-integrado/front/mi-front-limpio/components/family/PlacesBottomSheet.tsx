import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Keyboard, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { HomePlusIcon, type HomePlusIconName } from '../../constants/icons';
import { radius, spacing, touchTargets } from '../../constants/theme';
import { ActionSheet, AppButton, AppCard, AppInput, AppText, FormActionRow, IconButton, InteractivePressable } from '../ui';

export type PlaceCategory = 'home' | 'school' | 'work' | 'supermarket' | 'club' | 'family' | 'other';

export type FamilyPlace = {
  id: string;
  name: string;
  category: PlaceCategory;
  address: string;
  locality?: string;
  latitude: number;
  longitude: number;
  radiusMeters: number;
  membersPresent?: number;
};

export type PlaceDraft = Omit<FamilyPlace, 'id' | 'membersPresent'>;

export type NearbyPlace = {
  id: string;
  name: string;
  category: PlaceCategory;
  address: string;
  locality?: string;
  distance: string;
  latitude: number;
  longitude: number;
};

const CATEGORIES: readonly { id: PlaceCategory; label: string; icon: HomePlusIconName }[] = [
  { id: 'home', label: 'Casa', icon: 'home-outline' },
  { id: 'school', label: 'Escuela', icon: 'school-outline' },
  { id: 'work', label: 'Trabajo', icon: 'briefcase-outline' },
  { id: 'supermarket', label: 'Supermercado', icon: 'cart-outline' },
  { id: 'club', label: 'Club', icon: 'football-outline' },
  { id: 'family', label: 'Familiar', icon: 'heart-outline' },
  { id: 'other', label: 'Otro', icon: 'location-outline' },
];

export const PLACE_SUGGESTIONS: readonly { category: PlaceCategory; label: string }[] = [
  { category: 'home', label: 'Agregá tu casa' },
  { category: 'school', label: 'Agregá tu escuela' },
  { category: 'work', label: 'Agregá tu trabajo' },
  { category: 'supermarket', label: 'Agregá tu supermercado' },
];

export const getPlaceCategory = (category: PlaceCategory) => CATEGORIES.find((item) => item.id === category) ?? CATEGORIES.at(-1)!;
export const getPlaceIcon = (category: PlaceCategory) => getPlaceCategory(category).icon;
export const getPlaceCategoryLabel = (category: PlaceCategory) => getPlaceCategory(category).label;

export const createPlaceDraft = (category: PlaceCategory = 'other', seed?: Partial<PlaceDraft>): PlaceDraft => ({
  name: category === 'other' ? '' : getPlaceCategoryLabel(category),
  category,
  address: '',
  locality: '',
  latitude: -34.6037,
  longitude: -58.3816,
  radiusMeters: 100,
  ...seed,
});

export function PlaceRow({ place, onPress }: { place: FamilyPlace; onPress: () => void }) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const category = getPlaceCategory(place.category);
  const presence = place.membersPresent ? `${place.membersPresent} ${place.membersPresent === 1 ? 'integrante ahora' : 'integrantes ahora'}` : null;
  return (
    <InteractivePressable
      accessibilityRole="button"
      accessibilityLabel={`${place.name}. ${place.address}.${presence ? ` ${presence}.` : ''}`}
      accessibilityHint="Centra el mapa y muestra este lugar"
      onPress={onPress}
      haptic="light"
      pressScale={0.985}
      style={styles.placeRow}
    >
      <View style={styles.categoryIcon}><HomePlusIcon name={category.icon} size={22} color={colors.brand} /></View>
      <View style={styles.rowText}>
        <AppText variant="body" weight="700">{place.name}</AppText>
        <AppText variant="caption" tone="secondary">{place.address}</AppText>
        {presence ? <AppText variant="caption" tone="success" weight="700">{presence}</AppText> : null}
      </View>
      <HomePlusIcon name="chevron-forward-outline" size={20} color={colors.text.tertiary} />
    </InteractivePressable>
  );
}

export function PlaceSuggestionRow({ category, label, onAdd }: { category: PlaceCategory; label: string; onAdd: () => void }) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  return (
    <View style={styles.suggestionRow}>
      <View style={[styles.suggestionIcon, { backgroundColor: colors.brandSoft }]}><HomePlusIcon name={getPlaceIcon(category)} size={19} color={colors.brandPressed} /></View>
      <AppText variant="bodySmall" weight="700" style={styles.rowText}>{label}</AppText>
      <AppButton title="Agregar" size="sm" variant="secondary" onPress={onAdd} accessibilityLabel={`${label}. Agregar`} />
    </View>
  );
}

type PlacesBottomSheetProps = {
  visible: boolean;
  places: FamilyPlace[];
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
  onRetry?: () => void;
  onSelectPlace: (place: FamilyPlace) => void;
  onStartAdd: (category?: PlaceCategory) => void;
};

export function PlacesBottomSheet({ visible, places, loading = false, error, onClose, onRetry, onSelectPlace, onStartAdd }: PlacesBottomSheetProps) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const hasPlaces = places.length > 0;
  return (
    <ActionSheet visible={visible} title="Lugares" subtitle="Accesos útiles para tu hogar" onRequestClose={onClose} size="near-full">
      <ScrollView contentContainerStyle={styles.sheetContent} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
        <View style={styles.sheetTitleRow}>
          <AppText variant="caption" tone="tertiary" weight="700" style={styles.sectionLabel}>GUARDADOS</AppText>
          {hasPlaces ? <IconButton icon="add" variant="brandSoft" accessibilityLabel="Agregar lugar" onPress={() => onStartAdd()} /> : null}
        </View>
        {loading ? <View style={styles.stateCard}><AppText variant="bodySmall" weight="700">Cargando lugares...</AppText></View> : null}
        {error ? <View style={styles.stateCard}><AppText variant="bodySmall" weight="700">No pudimos cargar los lugares</AppText><AppText variant="caption" tone="secondary">{error}</AppText>{onRetry ? <AppButton title="Reintentar" variant="secondary" size="sm" onPress={onRetry} /> : null}</View> : null}
        {!loading && !error && places.length === 0 ? (
          <View style={styles.emptyState}>
            <View style={styles.emptyIcon}><HomePlusIcon name="location-outline" size={28} color={colors.brand} /></View>
            <AppText variant="title3" weight="800" align="center">Todavía no agregaste lugares</AppText>
            <AppText variant="bodySmall" tone="secondary" align="center">Guardá los lugares que usa tu familia para ubicarlos más rápido.</AppText>
            <AppButton title="Agregar primer lugar" onPress={() => onStartAdd()} accessibilityLabel="Agregar el primer lugar" />
          </View>
        ) : null}
        {!loading && !error && places.length > 0 ? <View style={styles.listCard}>{places.map((place) => <PlaceRow key={place.id} place={place} onPress={() => onSelectPlace(place)} />)}</View> : null}
        <AppText variant="caption" tone="tertiary" weight="700" style={styles.sectionLabel}>SUGERENCIAS</AppText>
        <View style={styles.listCard}>{PLACE_SUGGESTIONS.map((suggestion) => <PlaceSuggestionRow key={suggestion.category} {...suggestion} onAdd={() => onStartAdd(suggestion.category)} />)}</View>
      </ScrollView>
    </ActionSheet>
  );
}

type PlaceSearchSheetProps = {
  visible: boolean;
  hasLocation: boolean;
  locatingCurrentLocation?: boolean;
  currentLocationError?: string | null;
  onClose: () => void;
  onSearch: (query: string) => Promise<NearbyPlace[]>;
  onSelect: (result: NearbyPlace) => void;
  onUseCurrentLocation: () => void;
  onPickOnMap: () => void;
};

export function PlaceSearchSheet({
  visible,
  hasLocation,
  locatingCurrentLocation = false,
  currentLocationError,
  onClose,
  onSearch,
  onSelect,
  onUseCurrentLocation,
  onPickOnMap,
}: PlaceSearchSheetProps) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<NearbyPlace[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const searchAddress = async () => {
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 4 || searching) return;
    Keyboard.dismiss();
    setSearching(true);
    setSearchError(null);
    try {
      const nextResults = await onSearch(normalizedQuery);
      setResults(nextResults);
      setHasSearched(true);
    } catch {
      setResults([]);
      setHasSearched(true);
      setSearchError('No pudimos buscar esa dirección. Incluí calle, número, ciudad y país e intentá nuevamente.');
    } finally {
      setSearching(false);
    }
  };

  return (
    <ActionSheet visible={visible} title="Nuevo lugar" subtitle="Buscá, usá tu ubicación o elegí el punto" onRequestClose={onClose} size="scrollable-content" keyboardAware>
      <ScrollView contentContainerStyle={styles.sheetContent} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive" automaticallyAdjustKeyboardInsets>
        <AppInput
          label="Buscar calle, número, ciudad y país"
          variant="search"
          value={query}
          onChangeText={(value) => {
            setQuery(value);
            setHasSearched(false);
            setSearchError(null);
          }}
          autoFocus
          autoCorrect={false}
          returnKeyType="search"
          onSubmitEditing={() => { void searchAddress(); }}
          placeholder="Ej. Av. Italia 1234, Montevideo, Uruguay"
          accessibilityLabel="Buscar dirección"
        />
        <AppButton
          title={searching ? 'Buscando…' : 'Buscar dirección'}
          loading={searching}
          disabled={query.trim().length < 4 || searching}
          onPress={() => { void searchAddress(); }}
        />
        {hasLocation ? (
          <InteractivePressable
            accessibilityRole="button"
            accessibilityLabel={locatingCurrentLocation ? 'Buscando tu ubicación actual' : 'Usar mi ubicación actual'}
            accessibilityState={{ busy: locatingCurrentLocation, disabled: locatingCurrentLocation }}
            disabled={locatingCurrentLocation}
            onPress={() => {
              Keyboard.dismiss();
              onUseCurrentLocation();
            }}
            haptic="none"
            pressScale={0.985}
            style={styles.currentLocation}
          >
            {locatingCurrentLocation
              ? <ActivityIndicator size="small" color={colors.brand} />
              : <HomePlusIcon name="locate-outline" size={20} color={colors.brand} />}
            <View style={styles.rowText}>
              <AppText variant="bodySmall" weight="700" tone="brand">
                {locatingCurrentLocation ? 'Buscando tu ubicación…' : 'Usar mi ubicación actual'}
              </AppText>
              <AppText variant="caption" tone="secondary">Se obtiene del GPS del dispositivo, no del mapa.</AppText>
            </View>
          </InteractivePressable>
        ) : null}
        <InteractivePressable
          accessibilityRole="button"
          accessibilityLabel="Elegir la ubicación en el mapa"
          onPress={() => {
            Keyboard.dismiss();
            onPickOnMap();
          }}
          haptic="none"
          pressScale={0.985}
          style={styles.currentLocation}
        >
          <HomePlusIcon name="pin-outline" size={20} color={colors.brand} />
          <View style={styles.rowText}>
            <AppText variant="bodySmall" weight="700" tone="brand">Elegir en el mapa</AppText>
            <AppText variant="caption" tone="secondary">Mové el mapa hasta el punto exacto.</AppText>
          </View>
        </InteractivePressable>
        {currentLocationError ? <AppText variant="caption" tone="danger" accessibilityLiveRegion="polite">{currentLocationError}</AppText> : null}
        {searchError ? <AppText variant="caption" tone="danger" accessibilityLiveRegion="polite">{searchError}</AppText> : null}
        {results.length ? <><View style={styles.listCard}>{results.map((result) => <InteractivePressable key={result.id} accessibilityRole="button" accessibilityLabel={`${result.name}. ${result.address}${result.locality ? `, ${result.locality}` : ''}`} onPress={() => onSelect(result)} haptic="light" pressScale={0.985} style={styles.searchResult}><View style={styles.categoryIcon}><HomePlusIcon name={getPlaceIcon(result.category)} size={20} color={colors.brand} /></View><View style={styles.rowText}><AppText variant="bodySmall" weight="700">{result.name}</AppText><AppText variant="caption" tone="secondary">{result.address}</AppText>{result.locality ? <AppText variant="caption" tone="tertiary">{result.locality}</AppText> : null}</View><HomePlusIcon name="chevron-forward-outline" size={19} color={colors.text.tertiary} /></InteractivePressable>)}</View>{results.length === 1 ? <AppText variant="caption" tone="secondary" align="center">¿No es el lugar correcto? Sumá localidad, departamento y país, o elegilo en el mapa.</AppText> : null}</> : hasSearched && !searching && !searchError ? <View style={styles.emptyState}><AppText variant="body" weight="700">No encontramos resultados</AppText><AppText variant="bodySmall" tone="secondary" align="center">Incluí número, ciudad y país o elegí el punto manualmente en el mapa.</AppText></View> : null}
      </ScrollView>
    </ActionSheet>
  );
}

export function PlaceCategorySelector({ value, onChange }: { value: PlaceCategory; onChange: (category: PlaceCategory) => void }) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  return <View style={styles.categorySelector}>{CATEGORIES.map((category) => { const selected = value === category.id; return <InteractivePressable key={category.id} accessibilityRole="radio" accessibilityState={{ selected }} accessibilityLabel={category.label} onPress={() => onChange(category.id)} style={[styles.categoryChip, selected ? styles.categoryChipSelected : null]}><HomePlusIcon name={category.icon} size={18} color={selected ? colors.text.inverse : colors.text.secondary} /><AppText variant="caption" weight="700" tone={selected ? 'inverse' : 'secondary'}>{category.label}</AppText></InteractivePressable>; })}</View>;
}

export function PlaceForm({ visible, draft, saving = false, onClose, onChange, onSearchAddress, onChooseLocation, onChooseRadius, onSave }: { visible: boolean; draft: PlaceDraft; saving?: boolean; onClose: () => void; onChange: (draft: PlaceDraft) => void; onSearchAddress: () => void; onChooseLocation: () => void; onChooseRadius: () => void; onSave: () => void }) {
  const styles = useThemeStyles(createStylesForTheme);

  const [nameTouched, setNameTouched] = useState(false);
  useEffect(() => {
    if (visible) setNameTouched(false);
  }, [visible, draft.latitude, draft.longitude]);
  const nameMissing = !draft.name.trim();
  const nameError = nameTouched && nameMissing ? 'Ingresá un nombre para este lugar.' : undefined;
  return <ActionSheet visible={visible} title="Confirmar lugar" subtitle="Podés cambiar el nombre antes de guardarlo" onRequestClose={onClose} closeDisabled={saving} size="near-full" keyboardAware footer={<AppButton title="Guardar lugar" loading={saving} disabled={nameMissing || !draft.address.trim()} onPress={onSave} accessibilityLabel="Guardar lugar" />}><ScrollView contentContainerStyle={styles.sheetContent} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive" automaticallyAdjustKeyboardInsets><AppInput label="Nombre" value={draft.name} onChangeText={(name) => onChange({ ...draft, name })} onBlur={() => setNameTouched(true)} placeholder="Ej. Casa" errorText={nameError} autoCapitalize="sentences" /><View style={styles.formSection}><AppText variant="caption" tone="secondary" weight="700">Categoría</AppText><PlaceCategorySelector value={draft.category} onChange={(category) => onChange({ ...draft, category, name: draft.name || (category === 'other' ? '' : getPlaceCategoryLabel(category)) })} /></View><FormActionRow label="Dirección" value={draft.address || 'Buscar dirección'} onPress={onSearchAddress} accessibilityLabel={draft.address ? `Cambiar dirección, ${draft.address}` : 'Buscar dirección'} /><FormActionRow label="Ubicación" value="Ajustar en el mapa" onPress={onChooseLocation} accessibilityLabel="Modificar ubicación en el mapa" /><FormActionRow label="Zona del lugar" value={`${draft.radiusMeters} m`} onPress={onChooseRadius} accessibilityLabel={`Zona del lugar, ${draft.radiusMeters} metros`} /></ScrollView></ActionSheet>;
}

export function PlaceRadiusSheet({ visible, value, onClose, onChange }: { visible: boolean; value: number; onClose: () => void; onChange: (radius: number) => void }) {
  const styles = useThemeStyles(createStylesForTheme);

  const options = [50, 100, 200, 300];
  return <ActionSheet visible={visible} title="Zona del lugar" subtitle="Elegí el radio para detectar entradas y salidas" onRequestClose={onClose} size="content"><View style={styles.radiusPreview}><View style={[styles.radiusCircle, { width: Math.min(132, 62 + value / 3), height: Math.min(132, 62 + value / 3) }]}><AppText variant="body" weight="800">{value} m</AppText></View></View><View style={styles.radiusOptions}>{options.map((option) => <InteractivePressable key={option} accessibilityRole="radio" accessibilityState={{ selected: value === option }} accessibilityLabel={`${option} metros`} onPress={() => onChange(option)} style={[styles.radiusOption, value === option ? styles.radiusOptionSelected : null]}><AppText variant="bodySmall" weight="700" tone={value === option ? 'inverse' : 'primary'}>{option} m</AppText></InteractivePressable>)}</View></ActionSheet>;
}

export function PlaceLocationPicker({ visible, address, bottomInset = 0, isResolving = false, onBack, onRecenter, onUseLocation }: { visible: boolean; address: string; bottomInset?: number; isResolving?: boolean; onBack: () => void; onRecenter: () => void; onUseLocation: () => void }) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const insets = useSafeAreaInsets();
  if (!visible) return null;
  return <View style={[styles.mapPickerOverlay, { paddingTop: Math.max(insets.top, spacing[3]), paddingBottom: Math.max(insets.bottom, spacing[3]) + bottomInset }]} pointerEvents="box-none"><View style={styles.mapPickerTop} pointerEvents="auto"><AppButton variant="glass" size="sm" leftSlot={<HomePlusIcon name="arrow-back" size={19} color={colors.text.primary} />} title="Elegir ubicación" onPress={onBack} accessibilityLabel="Volver a agregar lugar" /></View><View pointerEvents="none" style={styles.fixedPin}><View style={styles.pinCircle}><HomePlusIcon name="location" size={30} color={colors.text.inverse} /></View><View style={styles.pinPoint} /></View><View style={styles.mapPickerBottom} pointerEvents="auto"><AppCard variant="glass" padding="generous" style={styles.locationCard}><View style={styles.locationHeader}><View style={styles.rowText}><AppText variant="body" weight="800">Mové el mapa para ubicar el lugar</AppText><AppText variant="bodySmall" tone="secondary">{isResolving ? 'Buscando dirección...' : address || 'Ubicación seleccionada en el mapa'}</AppText></View><IconButton icon="locate" variant="brandSoft" accessibilityLabel="Recentrar mapa" onPress={onRecenter} disabled={isResolving} /></View><AppButton title={isResolving ? 'Buscando dirección…' : 'Usar esta ubicación'} loading={isResolving} disabled={isResolving} onPress={onUseLocation} /></AppCard></View></View>;
}



function createStylesForTheme({ colors, shadows }: Pick<AppResolvedTheme, 'colors' | 'shadows'>) {
  return StyleSheet.create({
  sheetContent: { paddingBottom: spacing[4], gap: spacing[3] },
  sheetTitleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sectionLabel: { letterSpacing: 0.8, marginTop: spacing[1] },
  listCard: { backgroundColor: colors.surface.card, borderWidth: 1, borderColor: colors.border.subtle, borderRadius: radius.lg, overflow: 'hidden' },
  placeRow: { minHeight: 78, padding: spacing[3], flexDirection: 'row', alignItems: 'center', gap: spacing[3], borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border.subtle },
  nearbyRow: { minHeight: 78, padding: spacing[3], flexDirection: 'row', alignItems: 'center', gap: spacing[3], borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border.subtle },
  suggestionRow: { minHeight: 64, padding: spacing[3], flexDirection: 'row', alignItems: 'center', gap: spacing[3], borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border.subtle },
  categoryIcon: { width: 44, height: 44, borderRadius: radius.full, backgroundColor: colors.background.soft, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  suggestionIcon: { width: 36, height: 36, borderRadius: radius.full, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  rowText: { flex: 1, gap: 2, minWidth: 0 },
  emptyState: { paddingVertical: spacing[6], paddingHorizontal: spacing[5], gap: spacing[3], alignItems: 'center', backgroundColor: colors.surface.soft, borderRadius: radius.lg },
  emptyIcon: { width: 56, height: 56, borderRadius: radius.full, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' },
  stateCard: { padding: spacing[4], gap: spacing[2], backgroundColor: colors.surface.soft, borderRadius: radius.lg },
  permissionState: { padding: spacing[5], backgroundColor: colors.surface.soft, borderRadius: radius.lg, alignItems: 'center', gap: spacing[2] },
  currentLocation: { minHeight: touchTargets.normal, flexDirection: 'row', alignItems: 'center', gap: spacing[3], alignSelf: 'stretch', paddingHorizontal: spacing[2], paddingVertical: spacing[2], borderRadius: radius.md },
  searchResult: { minHeight: 72, padding: spacing[3], flexDirection: 'row', alignItems: 'center', gap: spacing[3], borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border.subtle },
  formSection: { gap: spacing[2] },
  categorySelector: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  categoryChip: { minHeight: touchTargets.normal, paddingHorizontal: spacing[3], borderRadius: radius.full, backgroundColor: colors.surface.soft, borderWidth: 1, borderColor: colors.border.default, flexDirection: 'row', alignItems: 'center', gap: spacing[1] },
  categoryChipSelected: { backgroundColor: colors.brand, borderColor: colors.brand },
  radiusPreview: { height: 150, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background.soft, borderRadius: radius.lg, overflow: 'hidden' },
  radiusCircle: { borderRadius: radius.full, borderWidth: 2, borderColor: colors.brand, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' },
  radiusOptions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2], marginTop: spacing[3] },
  radiusOption: { minHeight: touchTargets.normal, minWidth: 72, paddingHorizontal: spacing[3], borderRadius: radius.full, borderWidth: 1, borderColor: colors.border.default, backgroundColor: colors.surface.card, alignItems: 'center', justifyContent: 'center' },
  radiusOptionSelected: { backgroundColor: colors.brand, borderColor: colors.brand },
  mapPickerOverlay: { ...StyleSheet.absoluteFill, zIndex: 8, justifyContent: 'space-between', padding: spacing[3] },
  mapPickerTop: { alignSelf: 'flex-start' },
  fixedPin: { position: 'absolute', top: '43%', left: '50%', marginLeft: -22, alignItems: 'center' },
  pinCircle: { width: 44, height: 44, borderRadius: radius.full, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center', ...shadows.shadow2 },
  pinPoint: { width: 4, height: 16, backgroundColor: colors.brand, marginTop: -2, borderBottomLeftRadius: radius.full, borderBottomRightRadius: radius.full },
  mapPickerBottom: { width: '100%' },
  locationCard: { borderRadius: radius.xl, gap: spacing[3], ...shadows.sheet },
  locationHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
});
}
