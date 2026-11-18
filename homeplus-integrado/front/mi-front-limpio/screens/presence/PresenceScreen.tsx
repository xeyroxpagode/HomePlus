import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Image, Linking, Platform, StyleSheet, View } from 'react-native';
import * as Location from 'expo-location';
import Constants from 'expo-constants';
import MapView, { Circle, Marker, type Region } from 'react-native-maps';
import { useNavigation } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  AppCard,
  AppScreen,
  AppText,
  EmptyState,
  ErrorState,
  floatingNavigationMetrics,
  IconButton,
  InteractivePressable,
} from '../../components/ui';
import {
  MapContextCard,
  MapContextActions,
  mapContextActionsHeight,
  PlaceForm,
  PlaceLocationPicker,
  PlaceRadiusSheet,
  PlaceSearchSheet,
  PlacesBottomSheet,
  createPlaceDraft,
  getPlaceIcon,
  type FamilyPlace,
  type NearbyPlace,
  type PlaceCategory,
  type PlaceDraft,
  type MapContextCardMode,
} from '../../components/family';
import { HomePlusIcon } from '../../constants/icons';
import { radius, spacing } from '../../constants/theme';
import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import {
  fetchPresenceLocations,
  mergePresenceMembers,
  shouldApplyPresenceMember,
  type PresenceMember,
  type PresenceMemberLocation,
} from '../../services/presence';
import { useLocationSharing, type PublishedPresenceLocation } from '../../services/presenceLocationSharing';
import { presenceDiagnostics } from '../../services/presenceDiagnostics';
import { supabase } from '../../supabase';
import { PresenceDiagnosticsPanel } from '../../components/presence/PresenceDiagnosticsPanel';

const IS_DEVELOPMENT = typeof __DEV__ !== 'undefined' && __DEV__;

const DEFAULT_REGION: Region = {
  latitude: -34.6037,
  longitude: -58.3816,
  latitudeDelta: 0.08,
  longitudeDelta: 0.08,
};

const FOCUSED_LOCATION_DELTA = 0.012;
const MAXIMUM_PLACE_FIX_ACCURACY_METERS = 50;

const formatDevicePlaceAddress = (
  geocoded: Location.LocationGeocodedAddress | undefined,
  latitude: number,
  longitude: number,
) => {
  const streetLine = [geocoded?.street, geocoded?.streetNumber].filter(Boolean).join(' ').trim();
  const localityParts = [geocoded?.city, geocoded?.district, geocoded?.region]
    .filter((part, index, values): part is string => Boolean(part) && values.indexOf(part) === index);
  const coordinateFallback = `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;

  return {
    address: geocoded?.formattedAddress?.trim() || streetLine || geocoded?.name?.trim() || coordinateFallback,
    locality: localityParts.join(', '),
  };
};

type PlacesFlow = 'list' | 'search' | 'search-map' | 'form' | 'radius' | null;

type PermissionState = 'unknown' | 'granted' | 'denied';
type MapContextSection = MapContextCardMode;
type RealtimeLocationRow = {
  household_id?: string;
  membership_id?: string;
  sharing_enabled?: boolean;
  latitude?: number | null;
  longitude?: number | null;
  accuracy_meters?: number | null;
  recorded_at?: string | null;
  updated_at?: string | null;
};

export type FamilyMapPanelProps = {
  embedded?: boolean;
};

const getMemberCoordinate = (member: PresenceMember) => {
  if (!member.location) return null;
  const { latitude, longitude } = member.location;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  return { latitude, longitude };
};

const getStatusLabel = (member: PresenceMember) => {
  if (member.status === 'live') return 'Compartiendo ubicación';
  if (member.status === 'stale') return 'Desactualizada';
  if (member.status === 'unavailable') return 'Sin ubicacion';
  return member.is_self ? 'No estas compartiendo' : 'No comparte';
};

const memberFromPublishedLocation = (
  member: PresenceMember,
  location: PublishedPresenceLocation,
): PresenceMember => ({
  ...member,
  sharing_enabled: true,
  presence_updated_at: location.updatedAt,
  status: 'live',
  location: {
    latitude: location.latitude,
    longitude: location.longitude,
    accuracy_meters: location.accuracyMeters,
    recorded_at: location.recordedAt,
    updated_at: location.updatedAt,
  },
});

const memberWithoutSharedLocation = (member: PresenceMember): PresenceMember => ({
  ...member,
  sharing_enabled: false,
  presence_updated_at: new Date().toISOString(),
  status: 'sharing_disabled',
  location: null,
});

const getRelativeTime = (iso: string | null | undefined, now = Date.now()) => {
  if (!iso) return 'Sin registro';
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return 'Ahora';
  if (minutes === 1) return 'Hace 1 min';
  if (minutes < 60) return `Hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours === 1 ? 'Hace 1 h' : `Hace ${hours} h`;
};

const isStale = (recordedAt: string | null | undefined) => {
  if (!recordedAt) return true;
  return Date.now() - new Date(recordedAt).getTime() > 10 * 60 * 1000;
};

const getInitials = (name: string) => name.trim().slice(0, 2).toUpperCase() || '?';

const abbreviateMembershipId = (value: string | null | undefined) => (
  value ? `${value.slice(0, 6)}...${value.slice(-4)}` : null
);

const PresenceMarker = React.memo(function PresenceMarker({
  member,
  onPress,
  onRendered,
}: {
  member: PresenceMember;
  onPress: () => void;
  onRendered: (details: {
    memberId: string;
    locationTimestamp: string | null;
    latitude: number;
    longitude: number;
  }) => void;
}) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const coordinate = getMemberCoordinate(member);
  const latitude = coordinate?.latitude ?? null;
  const longitude = coordinate?.longitude ?? null;

  useEffect(() => {
    if (latitude === null || longitude === null) return;
    onRendered({
      memberId: member.membership_id,
      locationTimestamp: member.location?.updated_at ?? member.location?.recorded_at ?? null,
      latitude,
      longitude,
    });
  }, [latitude, longitude, member.location?.recorded_at, member.location?.updated_at, member.membership_id, onRendered]);

  if (!coordinate) return null;

  const markerColor = member.is_self
    ? colors.brand
    : member.status === 'stale'
      ? colors.warning.base
      : colors.success.base;

  return (
    <Marker
      coordinate={coordinate}
      title={member.display_name}
      description={`${getStatusLabel(member)} - ${getRelativeTime(member.location?.recorded_at)}`}
      onPress={onPress}
    >
      <View style={[styles.memberMarker, { backgroundColor: markerColor }]}>
        {member.avatar_url ? (
          <Image source={{ uri: member.avatar_url }} style={styles.memberMarkerImage} />
        ) : (
          <AppText variant="caption" weight="700" style={styles.memberMarkerInitials}>
            {getInitials(member.display_name)}
          </AppText>
        )}
      </View>
    </Marker>
  );
});

const PlaceMarker = React.memo(function PlaceMarker({ place, onPress }: { place: FamilyPlace; onPress: () => void }) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  return (
    <Marker
      coordinate={{ latitude: place.latitude, longitude: place.longitude }}
      title={place.name}
      description={place.address}
      onPress={onPress}
    >
      <View style={styles.placeMarker}>
        <HomePlusIcon name={getPlaceIcon(place.category)} size={19} color={colors.text.inverse} />
      </View>
    </Marker>
  );
});

const memberFromRealtimeRow = (member: PresenceMember, row: RealtimeLocationRow): PresenceMember => {
  const sharingEnabled = Boolean(row.sharing_enabled);
  const hasCoordinates = sharingEnabled
    && Number.isFinite(row.latitude)
    && Number.isFinite(row.longitude)
    && Boolean(row.recorded_at);
  const location: PresenceMemberLocation | null = hasCoordinates
    ? {
      latitude: row.latitude as number,
      longitude: row.longitude as number,
      accuracy_meters: row.accuracy_meters ?? null,
      recorded_at: row.recorded_at as string,
      updated_at: row.updated_at ?? row.recorded_at as string,
    }
    : null;

  return {
    ...member,
    sharing_enabled: sharingEnabled,
    presence_updated_at: row.updated_at ?? row.recorded_at ?? member.presence_updated_at,
    status: !sharingEnabled
      ? 'sharing_disabled'
      : location && !isStale(location.recorded_at)
        ? 'live'
        : location
          ? 'stale'
          : 'unavailable',
    location,
  };
};

export function FamilyMapPanel({ embedded = false }: FamilyMapPanelProps) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const navigation = useNavigation<any>();
  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  const insets = useSafeAreaInsets();
  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? null;
  const sharing = useLocationSharing(accessToken, householdId);
  const mapRef = useRef<MapView | null>(null);
  const requestId = useRef(0);
  const membersRef = useRef<PresenceMember[]>([]);
  const hasCenteredOnOwnLocation = useRef(false);
  const hasFittedInitialLocations = useRef(false);
  const mapWasMovedByUser = useRef(false);
  const locatingPlaceRef = useRef(false);
  const [members, setMembers] = useState<PresenceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permissionState, setPermissionState] = useState<PermissionState>('unknown');
  const [contextSection, setContextSection] = useState<MapContextSection | null>(null);
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [showMemberPicker, setShowMemberPicker] = useState(false);
  const [relativeTimeNow, setRelativeTimeNow] = useState(() => Date.now());
  const [debugPanelVisible, setDebugPanelVisible] = useState(false);
  const [places, setPlaces] = useState<FamilyPlace[]>([]);
  const [placesFlow, setPlacesFlow] = useState<PlacesFlow>(null);
  const [placeDraft, setPlaceDraft] = useState<PlaceDraft>(() => createPlaceDraft());
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [editingPlaceId, setEditingPlaceId] = useState<string | null>(null);
  const [manualRegion, setManualRegion] = useState<Region>(DEFAULT_REGION);
  const [savingPlace, setSavingPlace] = useState(false);
  const [placeFeedback, setPlaceFeedback] = useState<string | null>(null);
  const [locatingPlace, setLocatingPlace] = useState(false);
  const [resolvingManualPlace, setResolvingManualPlace] = useState(false);
  const [placeLocationError, setPlaceLocationError] = useState<string | null>(null);
  const canRenderNativeMap = Platform.OS !== 'android'
    || Constants.appOwnership === 'expo'
    || Constants.expoConfig?.extra?.nativeCapabilities?.googleMapsAndroid === true;

  const visibleMembers = useMemo(
    () => members.filter((member) => getMemberCoordinate(member) && member.sharing_enabled),
    [members],
  );
  const myMember = useMemo(() => members.find((member) => member.is_self) ?? null, [members]);
  const isSharing = sharing.isSharing || Boolean(myMember?.sharing_enabled);
  const selectedMember = useMemo(
    () => members.find((member) => member.membership_id === selectedMemberId) ?? null,
    [members, selectedMemberId],
  );
  const selectedPlace = useMemo(
    () => places.find((place) => place.id === selectedPlaceId) ?? null,
    [places, selectedPlaceId],
  );
  const isPickingPlace = placesFlow === 'search-map';
  const debugMember = selectedMember ?? myMember;
  const getLiveRelativeTime = useCallback(
    (iso: string | null | undefined) => getRelativeTime(iso, relativeTimeNow),
    [relativeTimeNow],
  );

  const handleMarkerRendered = useCallback((details: {
    memberId: string;
    locationTimestamp: string | null;
    latitude: number;
    longitude: number;
  }) => {
    presenceDiagnostics.markerRendered(details);
    if (IS_DEVELOPMENT) {
      console.log('[PRESENCE:UI] marker.rendered', {
        membershipId: details.memberId,
        locationTimestamp: details.locationTimestamp,
      });
    }
  }, []);
  const initialRegion = useMemo(() => {
    const coordinate = visibleMembers[0] ? getMemberCoordinate(visibleMembers[0]) : null;
    return coordinate ? { ...DEFAULT_REGION, ...coordinate } : DEFAULT_REGION;
  }, [visibleMembers]);
  const mainNavigationOverlayBottom = floatingNavigationMetrics.mainRegularHeight
    + Math.max(insets.bottom, spacing[3])
    + spacing[2];
  const contextualContentBottom = mainNavigationOverlayBottom + mapContextActionsHeight + spacing[4];
  const standaloneContextualContentBottom = mapContextActionsHeight + spacing[8];
  const statusOverlayBottom = embedded ? contextualContentBottom : standaloneContextualContentBottom;

  const loadLocations = useCallback(async (showSpinner = false) => {
    if (!accessToken || !householdId) {
      setMembers([]);
      setLoading(false);
      return;
    }

    const currentRequest = ++requestId.current;
    if (showSpinner) setRefreshing(true);

    try {
      const response = await fetchPresenceLocations(accessToken);
      if (currentRequest !== requestId.current) return;
      if (response.household_id !== householdId) {
        throw new Error('presence_household_response_mismatch');
      }
      const nextMembers = mergePresenceMembers(membersRef.current, response.members);
      membersRef.current = nextMembers;
      setMembers(nextMembers);
      if (typeof __DEV__ !== 'undefined' && __DEV__) {
        const currentMembershipId = nextMembers.find((member) => member.is_self)?.membership_id ?? null;
        console.log('[PRESENCE:REALTIME] initialLocations.loaded', {
          householdId,
          currentMembershipId: abbreviateMembershipId(currentMembershipId),
          count: nextMembers.length,
          sharingCount: nextMembers.filter((member) => member.sharing_enabled).length,
        });
      }
      setError(null);
    } catch (caught) {
      if (currentRequest !== requestId.current) return;
      if (typeof __DEV__ !== 'undefined' && __DEV__) {
        console.log('[Presence] location load failed', caught instanceof Error ? caught.message : String(caught));
      }
      setError('No pudimos actualizar las ubicaciones. Revisá tu conexión e intentá nuevamente.');
    } finally {
      if (currentRequest === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [accessToken, householdId]);

  const refreshForegroundPermission = useCallback(async () => {
    if (Platform.OS === 'web') return;
    const permission = await Location.getForegroundPermissionsAsync();
    setPermissionState(permission.status === Location.PermissionStatus.GRANTED ? 'granted' : 'denied');
  }, []);

  const centerMapOn = useCallback((membershipId: string, coordinate: { latitude: number; longitude: number }) => {
    mapRef.current?.animateToRegion({
      latitude: coordinate.latitude,
      longitude: coordinate.longitude,
      latitudeDelta: FOCUSED_LOCATION_DELTA,
      longitudeDelta: FOCUSED_LOCATION_DELTA,
    }, 350);
    if (typeof __DEV__ !== 'undefined' && __DEV__) {
      console.log('[PRESENCE:UI] map.centerOn', { membershipId: abbreviateMembershipId(membershipId) });
    }
  }, []);

  const recenter = useCallback(() => {
    const selfCoordinate = myMember ? getMemberCoordinate(myMember) : null;
    const firstVisible = visibleMembers[0] ? getMemberCoordinate(visibleMembers[0]) : null;
    const target = selfCoordinate ?? firstVisible;
    const targetMember = selfCoordinate ? myMember : visibleMembers[0];
    if (target && targetMember) {
      mapWasMovedByUser.current = false;
      centerMapOn(targetMember.membership_id, target);
    }
  }, [centerMapOn, myMember, visibleMembers]);

  const focusMember = useCallback((member: PresenceMember) => {
    setSelectedMemberId(member.membership_id);
    setContextSection(member.is_self ? 'self' : 'members');
    setShowMemberPicker(false);
    const coordinate = getMemberCoordinate(member);
    if (coordinate) centerMapOn(member.membership_id, coordinate);
  }, [centerMapOn]);

  const focusPlace = useCallback((place: FamilyPlace) => {
    setSelectedPlaceId(place.id);
    setPlacesFlow(null);
    setContextSection('places');
    setShowMemberPicker(false);
    mapRef.current?.animateToRegion({
      latitude: place.latitude,
      longitude: place.longitude,
      latitudeDelta: FOCUSED_LOCATION_DELTA,
      longitudeDelta: FOCUSED_LOCATION_DELTA,
    }, 350);
  }, []);

  const startPlaceAdd = useCallback((category: PlaceCategory = 'other') => {
    setPlaceDraft(createPlaceDraft(category));
    setPlaceLocationError(null);
    setEditingPlaceId(null);
    setPlacesFlow(category === 'other' ? 'search' : 'form');
    setContextSection(null);
    setShowMemberPicker(false);
  }, []);

  const startPlaceFromResult = useCallback((result: NearbyPlace) => {
    setEditingPlaceId(null);
    setPlaceDraft(createPlaceDraft(result.category, {
      name: result.id === 'current-device-location' ? 'Mi ubicación' : result.name,
      address: result.address,
      locality: result.locality ?? '',
      latitude: result.latitude,
      longitude: result.longitude,
    }));
    mapRef.current?.animateToRegion({
      latitude: result.latitude,
      longitude: result.longitude,
      latitudeDelta: FOCUSED_LOCATION_DELTA,
      longitudeDelta: FOCUSED_LOCATION_DELTA,
    }, 300);
    setPlacesFlow('form');
  }, []);

  const searchPlacesByAddress = useCallback(async (query: string): Promise<NearbyPlace[]> => {
    if (Platform.OS === 'web') return [];
    if (Platform.OS === 'android') {
      const permission = await Location.getForegroundPermissionsAsync();
      if (permission.status !== Location.PermissionStatus.GRANTED) {
        throw new Error('foreground_location_permission_required');
      }
    }

    const matches = await Location.geocodeAsync(query);
    const candidates = matches.slice(0, 8);
    const resolved: NearbyPlace[] = [];
    for (const [index, candidate] of candidates.entries()) {
      let geocoded: Location.LocationGeocodedAddress | undefined;
      try {
        [geocoded] = await Location.reverseGeocodeAsync({
          latitude: candidate.latitude,
          longitude: candidate.longitude,
        });
      } catch {
        // The forward-geocoded coordinates remain valid even if the platform
        // cannot provide a normalized display address.
      }
      const formatted = formatDevicePlaceAddress(geocoded, candidate.latitude, candidate.longitude);
      const streetLine = [geocoded?.street, geocoded?.streetNumber].filter(Boolean).join(' ').trim();
      resolved.push({
        id: `geocoded-${candidate.latitude.toFixed(6)}-${candidate.longitude.toFixed(6)}-${index}`,
        name: streetLine || geocoded?.name?.trim() || query,
        category: 'other',
        address: geocoded ? formatted.address : query,
        locality: formatted.locality,
        latitude: candidate.latitude,
        longitude: candidate.longitude,
        distance: '',
      });
    }
    return resolved;
  }, []);

  const selectCurrentLocationForPlace = useCallback(async () => {
    if (locatingPlaceRef.current) return;
    locatingPlaceRef.current = true;
    setLocatingPlace(true);
    setPlaceLocationError(null);

    try {
      if (Platform.OS === 'web') throw new Error('location_unavailable_on_web');
      const permission = await Location.getForegroundPermissionsAsync();
      if (permission.status !== Location.PermissionStatus.GRANTED) {
        setPermissionState('denied');
        throw new Error('foreground_location_permission_required');
      }

      const servicesEnabled = await Location.hasServicesEnabledAsync();
      if (!servicesEnabled) throw new Error('location_services_disabled');

      const hasReducedAccuracy = Platform.OS === 'ios'
        ? permission.ios?.accuracy === 'reduced'
        : permission.android?.accuracy === 'coarse';
      if (hasReducedAccuracy) throw new Error('precise_location_required');

      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Highest });
      const { latitude, longitude } = position.coords;
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        throw new Error('invalid_device_coordinates');
      }
      if (position.coords.accuracy !== null
        && position.coords.accuracy > MAXIMUM_PLACE_FIX_ACCURACY_METERS) {
        throw new Error('device_location_not_precise_enough');
      }

      let geocoded: Location.LocationGeocodedAddress | undefined;
      try {
        [geocoded] = await Location.reverseGeocodeAsync({ latitude, longitude });
      } catch {
        // Coordinates are still authoritative when the platform geocoder is unavailable.
      }
      const resolvedAddress = formatDevicePlaceAddress(geocoded, latitude, longitude);
      startPlaceFromResult({
        id: 'current-device-location',
        name: 'Ubicación actual',
        category: 'other',
        address: resolvedAddress.address,
        locality: resolvedAddress.locality,
        latitude,
        longitude,
        distance: '',
      });
    } catch (caught) {
      if (typeof __DEV__ !== 'undefined' && __DEV__) {
        console.log('[Places] current device location failed', caught instanceof Error ? caught.message : String(caught));
      }
      const reason = caught instanceof Error ? caught.message : '';
      setPlaceLocationError(reason === 'precise_location_required'
        ? 'HomePlus tiene acceso aproximado. Activá Ubicación precisa para HomePlus en Configuración del iPhone.'
        : reason === 'device_location_not_precise_enough'
          ? 'La señal actual todavía es imprecisa. Acercate a una ventana, mantené Wi‑Fi activo e intentá nuevamente.'
          : 'No pudimos obtener una ubicación precisa. Revisá el permiso y que la ubicación del dispositivo esté activada.');
    } finally {
      locatingPlaceRef.current = false;
      setLocatingPlace(false);
    }
  }, [startPlaceFromResult]);

  const openManualPicker = useCallback(() => {
    const currentMemberCoordinate = myMember ? getMemberCoordinate(myMember) : null;
    const shouldUseCurrentMember = !placeDraft.address.trim() && currentMemberCoordinate;
    const latitude = shouldUseCurrentMember ? currentMemberCoordinate.latitude : placeDraft.latitude;
    const longitude = shouldUseCurrentMember ? currentMemberCoordinate.longitude : placeDraft.longitude;
    setManualRegion((current) => ({
      ...current,
      latitude,
      longitude,
    }));
    setPlacesFlow('search-map');
    mapRef.current?.animateToRegion({
      latitude,
      longitude,
      latitudeDelta: FOCUSED_LOCATION_DELTA,
      longitudeDelta: FOCUSED_LOCATION_DELTA,
    }, 250);
  }, [myMember, placeDraft.address, placeDraft.latitude, placeDraft.longitude]);

  const confirmManualLocation = useCallback(async () => {
    if (resolvingManualPlace) return;
    setResolvingManualPlace(true);
    let geocoded: Location.LocationGeocodedAddress | undefined;
    try {
      [geocoded] = await Location.reverseGeocodeAsync({
        latitude: manualRegion.latitude,
        longitude: manualRegion.longitude,
      });
    } catch {
      // Coordinates selected by the user remain authoritative.
    }
    const formatted = formatDevicePlaceAddress(geocoded, manualRegion.latitude, manualRegion.longitude);
    setPlaceDraft((current) => ({
      ...current,
      latitude: manualRegion.latitude,
      longitude: manualRegion.longitude,
      address: formatted.address,
      locality: formatted.locality,
    }));
    setResolvingManualPlace(false);
    setPlacesFlow('form');
  }, [manualRegion.latitude, manualRegion.longitude, resolvingManualPlace]);

  const savePlace = useCallback(() => {
    if (!placeDraft.name.trim() || !placeDraft.address.trim()) return;
    setSavingPlace(true);
    setTimeout(() => {
      const saved: FamilyPlace = { ...placeDraft, id: editingPlaceId ?? `place-${Date.now()}` };
      setPlaces((current) => editingPlaceId
        ? current.map((place) => place.id === editingPlaceId ? { ...place, ...saved } : place)
        : [...current, saved]);
      setSavingPlace(false);
      setPlacesFlow(null);
      setPlaceFeedback('Lugar guardado');
      focusPlace(saved);
    }, 280);
  }, [editingPlaceId, focusPlace, placeDraft]);

  const editSelectedPlace = useCallback(() => {
    if (!selectedPlace) return;
    const { id: _id, membersPresent: _membersPresent, ...draft } = selectedPlace;
    setPlaceDraft(draft);
    setEditingPlaceId(selectedPlace.id);
    setPlacesFlow('form');
    setContextSection(null);
  }, [selectedPlace]);

  const deleteSelectedPlace = useCallback(() => {
    if (!selectedPlace) return;
    Alert.alert('Eliminar lugar', `¿Querés eliminar ${selectedPlace.name}?`, [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'Eliminar',
        style: 'destructive',
        onPress: () => {
          setPlaces((current) => current.filter((place) => place.id !== selectedPlace.id));
          setSelectedPlaceId(null);
          setContextSection(null);
          setPlaceFeedback('Lugar eliminado');
        },
      },
    ]);
  }, [selectedPlace]);

  const handleContextSelect = useCallback((section: MapContextSection) => {
    if (section === 'places') {
      setPlacesFlow('list');
      setContextSection(null);
      setShowMemberPicker(false);
      return;
    }
    if (section === 'members') {
      if (contextSection === 'members' && showMemberPicker) {
        setContextSection(null);
        setShowMemberPicker(false);
      } else {
        setContextSection('members');
        setShowMemberPicker(true);
      }
      return;
    }

    if (contextSection === section) {
      setContextSection(null);
      setShowMemberPicker(false);
      return;
    }

    setContextSection(section);
    setShowMemberPicker(false);
    if (section === 'self' && myMember) setSelectedMemberId(myMember.membership_id);
  }, [contextSection, myMember, showMemberPicker]);

  const handleSharing = useCallback(async () => {
    setError(null);
    const result = isSharing ? await sharing.stop() : await sharing.start();
    if (!result.ok) setError(result.message);
    if (result.ok && isSharing) {
      setMembers((previous) => {
        const next = previous.map((member) => member.is_self
          ? memberWithoutSharedLocation(member)
          : member);
        membersRef.current = next;
        return next;
      });
    }
    await refreshForegroundPermission();
  }, [isSharing, refreshForegroundPermission, sharing]);

  const openLocationSettings = useCallback(() => {
    void Linking.openSettings().catch((caught) => {
      if (typeof __DEV__ !== 'undefined' && __DEV__) {
        console.log('[Presence] unable to open settings', caught instanceof Error ? caught.message : String(caught));
      }
    });
  }, []);

  useEffect(() => {
    const publishedLocation = sharing.lastPublishedLocation;
    const membershipId = myMember?.membership_id;
    if (!publishedLocation || !membershipId) return;

    setMembers((previous) => {
      const existing = previous.find((member) => member.membership_id === membershipId);
      if (existing?.location?.updated_at === publishedLocation.updatedAt && existing.sharing_enabled) return previous;

      const next = previous.map((member) => (
        member.membership_id === membershipId
          ? memberFromPublishedLocation(member, publishedLocation)
          : member
      ));
      membersRef.current = next;
      if (typeof __DEV__ !== 'undefined' && __DEV__) {
        console.log('[PRESENCE:UI] ownLocation.merged', { membershipId: abbreviateMembershipId(membershipId) });
        console.log('[PRESENCE:UI] state.location.updated', { membershipId: abbreviateMembershipId(membershipId) });
      }
      return next;
    });

    if (!hasCenteredOnOwnLocation.current && !mapWasMovedByUser.current) {
      hasCenteredOnOwnLocation.current = true;
      centerMapOn(membershipId, {
        latitude: publishedLocation.latitude,
        longitude: publishedLocation.longitude,
      });
    }
  }, [centerMapOn, myMember?.membership_id, sharing.lastPublishedLocation]);

  useEffect(() => {
    presenceDiagnostics.setDebugMember(debugMember?.membership_id ?? null);
  }, [debugMember?.membership_id]);

  useEffect(() => {
    void loadLocations(false);
    void refreshForegroundPermission();
    return () => {
      requestId.current += 1;
    };
  }, [loadLocations, refreshForegroundPermission]);

  useEffect(() => {
    const interval = setInterval(() => setRelativeTimeNow(Date.now()), 30_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!placeFeedback) return undefined;
    const timeout = setTimeout(() => setPlaceFeedback(null), 2_600);
    return () => clearTimeout(timeout);
  }, [placeFeedback]);

  useEffect(() => {
    if (!householdId) return undefined;

    const channel = supabase
      .channel(`presence-locations:${householdId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'presence_member_locations', filter: `household_id=eq.${householdId}` },
        (payload) => {
          const row = payload.new as RealtimeLocationRow;
          if (!row.membership_id || row.household_id !== householdId) return;

          const locationTimestamp = row.updated_at ?? row.recorded_at ?? null;
          presenceDiagnostics.realtimeEvent({
            memberId: row.membership_id,
            locationTimestamp,
            changedNormalizedState: null,
          });

          if (typeof __DEV__ !== 'undefined' && __DEV__) {
            console.log('[PRESENCE:REALTIME] received', {
              householdId,
              currentMembershipId: abbreviateMembershipId(membersRef.current.find((member) => member.is_self)?.membership_id),
              changedMembershipId: abbreviateMembershipId(row.membership_id),
              sharingEnabled: row.sharing_enabled === true,
              locationTimestamp,
            });
          }

          const knownMember = membersRef.current.some((member) => member.membership_id === row.membership_id);
          if (!knownMember) {
            presenceDiagnostics.realtimeEvent({
              memberId: row.membership_id,
              locationTimestamp,
              changedNormalizedState: false,
            });
            void loadLocations(false);
            return;
          }

          setMembers((previous) => {
            let changed = false;
            const next = previous.map((member) => {
              if (member.membership_id !== row.membership_id) return member;
              const incoming = memberFromRealtimeRow(member, row);
              if (!shouldApplyPresenceMember(member, incoming)) return member;
              changed = true;
              return incoming;
            });
            if (!changed) {
              presenceDiagnostics.realtimeEvent({
                memberId: row.membership_id!,
                locationTimestamp,
                changedNormalizedState: false,
              });
              return previous;
            }
            membersRef.current = next;
            presenceDiagnostics.realtimeEvent({
              memberId: row.membership_id!,
              locationTimestamp,
              changedNormalizedState: true,
            });
            if (typeof __DEV__ !== 'undefined' && __DEV__) {
              console.log('[PRESENCE:REALTIME] state.merged', { membershipId: abbreviateMembershipId(row.membership_id) });
              console.log('[PRESENCE:UI] marker.updated', { membershipId: abbreviateMembershipId(row.membership_id) });
            }
            return next;
          });
        },
      )
      .subscribe((status, subscriptionError) => {
        presenceDiagnostics.realtimeSubscription(status);
        if (typeof __DEV__ !== 'undefined' && __DEV__) {
          console.log('[PRESENCE:REALTIME] subscription', {
            householdId,
            status,
            error: subscriptionError?.message ?? null,
          });
        }
        if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          // A single read keeps the screen useful while Supabase reconnects;
          // normal updates continue to flow through the live channel.
          void loadLocations(false);
        }
      });

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [householdId, loadLocations]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState === 'active') {
        void refreshForegroundPermission();
        void loadLocations(false);
      }
    });
    return () => subscription.remove();
  }, [loadLocations, refreshForegroundPermission]);

  useEffect(() => {
    if (hasFittedInitialLocations.current || mapWasMovedByUser.current || visibleMembers.length < 2) return;
    const coordinates = visibleMembers
      .map(getMemberCoordinate)
      .filter((coordinate): coordinate is { latitude: number; longitude: number } => coordinate !== null);
    if (coordinates.length < 2) return;

    hasFittedInitialLocations.current = true;
    mapRef.current?.fitToCoordinates(coordinates, {
      animated: true,
      edgePadding: { top: 72, right: 40, bottom: 180, left: 40 },
    });
  }, [visibleMembers]);

  if (Platform.OS === 'web') {
    const fallback = <EmptyState title="GPS disponible en mobile" description="El mapa en vivo usa permisos nativos de ubicación." />;
    return embedded ? fallback : <AppScreen background="base" bottomInset="tab">{fallback}</AppScreen>;
  }

  const shareLabel = sharing.phase === 'requesting_permission'
    ? 'Solicitando permiso'
    : sharing.phase === 'getting_location'
      ? 'Obteniendo ubicación'
      : sharing.phase === 'stopping'
        ? 'Deteniendo'
        : isSharing
          ? 'Detener'
          : 'Compartir';
  const showBlockingError = Boolean(error && members.length === 0 && !loading);

  const mapContent = (
    <>
      {loading ? (
        <View style={styles.centerState}>
          <ActivityIndicator size="large" color={colors.brand} />
          <AppText variant="bodySmall" tone="secondary">Cargando mapa...</AppText>
        </View>
      ) : showBlockingError ? (
        <View style={styles.stateInset}>
          <ErrorState
            title="No pudimos actualizar las ubicaciones"
            description={error ?? 'Revisá tu conexión e intentá nuevamente.'}
            onRetry={() => void loadLocations(true)}
            secondaryActionLabel={sharing.requiresSettings ? 'Abrir configuración' : undefined}
            onSecondaryAction={sharing.requiresSettings ? openLocationSettings : undefined}
          />
        </View>
      ) : (
        <View style={[styles.mapWrap, embedded ? styles.embeddedMapWrap : null]}>
          {canRenderNativeMap ? (
            <MapView
              ref={mapRef}
              style={styles.map}
              initialRegion={initialRegion}
              showsUserLocation={permissionState === 'granted'}
              onPanDrag={() => { mapWasMovedByUser.current = true; }}
              onRegionChangeComplete={setManualRegion}
              onLongPress={IS_DEVELOPMENT ? () => setDebugPanelVisible(true) : undefined}
            >
              {myMember?.location && getMemberCoordinate(myMember) && Number.isFinite(myMember.location.accuracy_meters) ? (
                <Circle
                  center={getMemberCoordinate(myMember)!}
                  radius={Math.max(5, myMember.location.accuracy_meters ?? 0)}
                  fillColor="rgba(231, 100, 63, 0.10)"
                  strokeColor="rgba(231, 100, 63, 0.38)"
                  strokeWidth={1}
                />
              ) : null}
              {visibleMembers.map((member) => (
                <PresenceMarker
                  key={member.membership_id}
                  member={member}
                  onPress={() => focusMember(member)}
                  onRendered={handleMarkerRendered}
                />
              ))}
              {places.map((place) => (
                <PlaceMarker key={place.id} place={place} onPress={() => focusPlace(place)} />
              ))}
            </MapView>
          ) : (
            <View style={styles.mapConfigurationState} testID="presence.map.unavailable">
              <View style={styles.mapConfigurationIcon}>
                <HomePlusIcon name="map-outline" size={30} color={colors.brandPressed} />
              </View>
              <AppText variant="title3" align="center">Mapa no disponible en esta instalación</AppText>
              <AppText variant="bodySmall" tone="secondary" align="center">
                La aplicación sigue funcionando. Para mostrar el mapa, esta build de Android debe incluir la clave nativa de Google Maps.
              </AppText>
            </View>
          )}

          {!isPickingPlace ? <View style={[styles.floatingActions, embedded ? styles.embeddedFloatingActions : null]}>
            <IconButton icon="locate" onPress={recenter} accessibilityLabel="Centrar mapa" disabled={visibleMembers.length === 0} />
            <InteractivePressable
              accessibilityRole="button"
              accessibilityLabel={isSharing ? 'Detener ubicación compartida' : 'Compartir ubicación'}
              accessibilityState={{ busy: sharing.isUpdating }}
              disabled={sharing.isUpdating}
              onPress={() => void handleSharing()}
              haptic="light"
              pressScale={0.97}
              style={[styles.shareAction, isSharing ? styles.shareActionPaused : null]}
            >
              {sharing.isUpdating ? (
                <ActivityIndicator size="small" color={isSharing ? colors.brand : colors.text.inverse} />
              ) : (
                <AppText variant="bodySmall" weight="700" style={isSharing ? styles.shareActionPausedText : styles.shareActionText}>
                  {shareLabel}
                </AppText>
              )}
            </InteractivePressable>
          </View> : null}

          {error && members.length > 0 && !placeFeedback ? (
            <View style={[styles.statusOverlay, { bottom: statusOverlayBottom }]}>
              <AppCard variant="glass" padding="compact" style={styles.statusCard}>
                <AppText variant="caption" tone="secondary">{error}</AppText>
                {sharing.requiresSettings ? (
                  <InteractivePressable
                    accessibilityRole="button"
                    accessibilityLabel="Abrir configuración de ubicación"
                    onPress={openLocationSettings}
                    haptic="light"
                    style={styles.settingsAction}
                  >
                    <AppText variant="caption" weight="700" style={styles.settingsActionText}>Abrir configuración</AppText>
                  </InteractivePressable>
                ) : null}
              </AppCard>
            </View>
          ) : null}

          {visibleMembers.length === 0 && !contextSection && !isPickingPlace && !error && !placeFeedback ? (
            <View style={[styles.statusOverlay, { bottom: statusOverlayBottom }]}>
              <AppCard variant="glass" padding="compact" style={styles.statusCard}>
                <AppText variant="bodySmall" weight="700">Sin ubicaciones compartidas</AppText>
                <AppText variant="caption" tone="secondary">Activa compartir para mostrar tu posición al hogar.</AppText>
              </AppCard>
            </View>
          ) : null}

          {!isPickingPlace ? <View pointerEvents="box-none" style={[styles.contextualNavigationRail, embedded ? [styles.embeddedContextualNavigationRail, { bottom: mainNavigationOverlayBottom }] : null]}>
            <View pointerEvents="auto" style={styles.contextualNavigationContent}>
              {contextSection ? (
                <MapContextCard
                  mode={contextSection}
                  members={members}
                  selectedMember={selectedMember}
                  selectedPlace={selectedPlace ? {
                    id: selectedPlace.id,
                    name: selectedPlace.name,
                    detail: selectedPlace.address,
                    categoryLabel: selectedPlace.category,
                    membersPresent: selectedPlace.membersPresent,
                  } : null}
                  showMemberPicker={showMemberPicker}
                  getMemberStatus={getStatusLabel}
                  getRelativeTime={getLiveRelativeTime}
                  onSelectMember={focusMember}
                  onEditPlace={selectedPlace ? editSelectedPlace : undefined}
                  onDeletePlace={selectedPlace ? deleteSelectedPlace : undefined}
                />
              ) : null}
              <MapContextActions activeItem={contextSection} onSelect={handleContextSelect} />
            </View>
          </View> : null}

          {placeFeedback ? (
            <View style={[styles.statusOverlay, { bottom: statusOverlayBottom }]} pointerEvents="none">
              <AppCard variant="glass" padding="compact" style={styles.statusCard}><AppText variant="bodySmall" weight="700" tone="success">{placeFeedback}</AppText></AppCard>
            </View>
          ) : null}

          <PlaceLocationPicker
            visible={isPickingPlace}
            address={placeDraft.address}
            bottomInset={embedded ? mainNavigationOverlayBottom : 0}
            isResolving={resolvingManualPlace}
            onBack={() => setPlacesFlow(placeDraft.address.trim() ? 'form' : 'search')}
            onRecenter={recenter}
            onUseLocation={() => { void confirmManualLocation(); }}
          />

          <PresenceDiagnosticsPanel
            visible={debugPanelVisible}
            onClose={() => setDebugPanelVisible(false)}
          />
        </View>
      )}
      {refreshing ? null : null}
    </>
  );

  const placeSheets = (
    <>
      <PlacesBottomSheet
        visible={placesFlow === 'list'}
        places={places}
        onClose={() => setPlacesFlow(null)}
        onSelectPlace={focusPlace}
        onStartAdd={startPlaceAdd}
      />
      <PlaceSearchSheet
        visible={placesFlow === 'search'}
        hasLocation={permissionState === 'granted'}
        locatingCurrentLocation={locatingPlace}
        currentLocationError={placeLocationError}
        onClose={() => {
          setPlaceLocationError(null);
          setPlacesFlow(placeDraft.address.trim() ? 'form' : 'list');
        }}
        onSearch={searchPlacesByAddress}
        onSelect={startPlaceFromResult}
        onUseCurrentLocation={() => { void selectCurrentLocationForPlace(); }}
        onPickOnMap={openManualPicker}
      />
      <PlaceForm
        visible={placesFlow === 'form'}
        draft={placeDraft}
        saving={savingPlace}
        onClose={() => {
          if (editingPlaceId && selectedPlace) {
            focusPlace(selectedPlace);
            return;
          }
          setPlacesFlow('list');
        }}
        onChange={setPlaceDraft}
        onSearchAddress={() => setPlacesFlow('search')}
        onChooseLocation={openManualPicker}
        onChooseRadius={() => setPlacesFlow('radius')}
        onSave={savePlace}
      />
      <PlaceRadiusSheet
        visible={placesFlow === 'radius'}
        value={placeDraft.radiusMeters}
        onClose={() => setPlacesFlow('form')}
        onChange={(radiusMeters) => {
          setPlaceDraft((current) => ({ ...current, radiusMeters }));
          setPlacesFlow('form');
        }}
      />
    </>
  );

  if (embedded) return <View style={styles.embeddedRoot}>{mapContent}{placeSheets}</View>;

  return (
    <AppScreen padded={false} background="base" bottomInset="tab">
      <View style={styles.header}>
        <View style={styles.standaloneHeaderRow}>
          {navigation.canGoBack() ? (
            <IconButton
              icon="chevron-back-outline"
              variant="plain"
              onPress={() => navigation.goBack()}
              accessibilityLabel="Volver a Más"
            />
          ) : null}
          <View style={styles.standaloneHeaderCopy}>
            <AppText variant="title2">Ubicación familiar</AppText>
            <AppText variant="bodySmall" tone="secondary">Compartís solo cuando lo activás.</AppText>
          </View>
        </View>
      </View>
      {mapContent}
      {placeSheets}
    </AppScreen>
  );
}

export function PresenceScreen() {
  return <FamilyMapPanel />;
}



function createStylesForTheme({ colors, shadows }: Pick<AppResolvedTheme, 'colors' | 'shadows'>) {
  return StyleSheet.create({
  header: { paddingHorizontal: spacing[5], paddingTop: spacing[4], paddingBottom: spacing[3] },
  standaloneHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] },
  standaloneHeaderCopy: { flex: 1, gap: spacing[1] },
  centerState: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing[3] },
  stateInset: { paddingHorizontal: spacing[5], paddingTop: spacing[4] },
  mapWrap: { minHeight: 460, flex: 1, overflow: 'hidden', borderRadius: radius.xl },
  embeddedRoot: { flex: 1 },
  embeddedMapWrap: { minHeight: 0 },
  map: { flex: 1 },
  mapConfigurationState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing[3],
    paddingHorizontal: spacing[8],
    backgroundColor: colors.background.soft,
  },
  mapConfigurationIcon: {
    width: 56,
    height: 56,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.terracotta[100],
    borderWidth: 1,
    borderColor: colors.terracotta[300],
  },
  floatingActions: { position: 'absolute', top: spacing[3], right: spacing[3], flexDirection: 'row', gap: spacing[2], alignItems: 'center', zIndex: 3, elevation: 3 },
  embeddedFloatingActions: { top: 72 },
  shareAction: { minHeight: 44, paddingHorizontal: spacing[4], borderRadius: radius.full, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand, ...shadows.shadow2 },
  shareActionPaused: { backgroundColor: colors.surface.glass, borderWidth: 1, borderColor: colors.border.subtle },
  shareActionText: { color: colors.text.inverse },
  shareActionPausedText: { color: colors.brand },
  statusOverlay: { position: 'absolute', left: spacing[3], right: spacing[3], alignItems: 'center', zIndex: 3, elevation: 3 },
  statusCard: { width: '100%', maxWidth: 420 },
  settingsAction: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center', marginTop: spacing[1] },
  settingsActionText: { color: colors.brand },
  contextualNavigationRail: { position: 'absolute', left: spacing[3], right: spacing[3], bottom: spacing[4], zIndex: 4, elevation: 4 },
  embeddedContextualNavigationRail: { bottom: spacing[2] },
  contextualNavigationContent: { gap: spacing[2] },
  memberMarker: {
    width: 42,
    height: 42,
    borderRadius: radius.full,
    borderWidth: 3,
    borderColor: colors.surface.card,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadows.shadow2,
  },
  memberMarkerImage: {
    width: 36,
    height: 36,
    borderRadius: radius.full,
  },
  memberMarkerInitials: { color: colors.text.inverse },
  placeMarker: {
    width: 38,
    height: 38,
    borderRadius: radius.full,
    backgroundColor: colors.brand,
    borderWidth: 3,
    borderColor: colors.surface.card,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadows.shadow2,
  },
});
}
