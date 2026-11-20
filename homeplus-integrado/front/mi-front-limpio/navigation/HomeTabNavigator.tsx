import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { ActivityIndicator, Keyboard, Platform, View, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { createBottomTabNavigator, type BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { HomeTabParamList, MoreStackParamList, PlannerStackParamList } from './types';
import { useAuth } from '../context/AuthContext';
import { useHousehold } from '../context/HouseholdContext';
import { HomeCoordinador } from '../screens/home/HomeCoordinador';
import { HomeAdulto } from '../screens/home/HomeAdulto';
import { HomeAdolescente } from '../screens/home/HomeAdolescente';
import { HomeAdultoMayor } from '../screens/home/HomeAdultoMayor';
import { FamilyScreen } from '../screens/FamilyScreen';
import { HomeCloudScreen } from '../screens/HomeCloudScreen';
import { HomeCloudScannerScreen } from '../screens/HomeCloudScannerScreen';
import { FinanceScreen } from '../screens/finance/FinanceScreen';
import { InventarioScreen } from '../screens/inventory/InventarioScreen';
import { InventoryShoppingListScreen } from '../screens/inventory/InventoryShoppingListScreen';
import { InventoryPurchaseScreen } from '../screens/inventory/InventoryPurchaseScreen';
import { PlannerScreen } from '../screens/planner/PlannerScreen';
import { CreateTaskScreen } from '../screens/planner/CreateTaskScreen';
import { EditTaskScreen } from '../screens/planner/EditTaskScreen';
import { CreateEventScreen } from '../screens/planner/CreateEventScreen';
import { EditEventScreen } from '../screens/planner/EditEventScreen';
import { CreateGoalScreen } from '../screens/planner/CreateGoalScreen';
import { PlannerPlanStructureEditScreen } from '../screens/planner/PlannerPlanStructureEditScreen';
import { PlannerPlanDetailScreen } from '../screens/planner/PlannerPlanDetailScreen';
import { PlannerPlanCreateScreen } from '../screens/planner/PlannerPlanCreateScreen';
import { PlannerPlanListScreen } from '../screens/planner/PlannerPlanListScreen';
import { PlannerPlanDetailScreen as PlannerPlanDetailScreenV1 } from '../screens/planner/PlannerPlanDetailScreenV1';
import { PlannerTrashScreen } from '../screens/planner/PlannerTrashScreen';
import { PlannerSearchScreen } from '../screens/planner/PlannerSearchScreen';
import { PlannerAttentionActivityScreen } from '../screens/planner/PlannerAttentionActivityScreen';
import { TaskDetailScreen } from '../screens/planner/TaskDetailScreen';
import { EventDetailScreen } from '../screens/planner/EventDetailScreen';
import { ResponsibilitiesScreen } from '../screens/planner/ResponsibilitiesScreen';
import { ResponsibilityFormScreen } from '../screens/planner/ResponsibilityFormScreen';
import { ResponsibilityDetailScreen } from '../screens/planner/ResponsibilityDetailScreen';
import {
  PlannerDraftRecoveryRoute,
  PlannerDraftResumeRoute,
  PlannerPresetCreateRoute,
  PlannerPresetDetailRoute,
  PlannerPresetDraftsTrashRoute,
  PlannerPresetEditRoute,
  PlannerPresetLibraryRoute,
} from '../components/planner/presets/PlannerPresetDraftsIntegrationRoutes';
import { MoreScreen } from '../screens/MoreScreen';
import {
  AssetsArchivedScreen,
  AssetsRootScreen,
  AssetsTrashScreen,
} from '../screens/assets/AssetsListScreen';
import { AssetDetailScreen } from '../screens/assets/AssetDetailScreen';
import { AssetCareScreen, AssetRecordsScreen } from '../screens/assets/AssetRecordsScreen';
import { FinanceAccountsScreen } from '../screens/finance/FinanceAccountsScreen';
import { FinancePapeleraScreen } from '../screens/finance/FinancePapeleraScreen';
import { FinancePoolManagementScreen } from '../components/finance/FinancePoolManagementScreen';
import { FinanceSpendingLimitsManagementScreen } from '../components/finance/FinanceSpendingLimitsManagementScreen';
import { FinanceCategoryManagementScreen } from '../components/finance/FinanceCategoryManagementScreen';
import { FinanceAnalysisDetailScreen } from '../screens/finance/FinanceAnalysisDetailScreen';
import { PresenceScreen } from '../screens/presence/PresenceScreen';
import { HomiScreen } from '../screens/homi/HomiScreen';
import {
  AppTopBar,
  AccountSheet,
  AppText,
  FloatingNavigationBar,
  type FloatingNavigationItem,
  HouseholdSwitcherSheet,
  IconButton,
} from '../components/ui';
import { PlannerSheetProvider, usePlannerSheet } from '../context/PlannerSheetContext';
import { PlannerSheetHost } from '../components/planner/PlannerSheetHost';
import { PlannerDeepLinkProvider } from '../services/planner/plannerDeepLinkProvider';
import { fetchPlannerAttentionRequest } from '../services/planner/plannerAttentionClient';
import { GLOBAL_SURFACE_GATES_OFF } from '../services/planner/globalSurfaceTypes';
import { colors, spacing } from '../constants/theme';
import { DEFAULT_SETTINGS_ORIGIN, type SettingsOriginTab } from './settingsNavigation';
import { useMessaging } from '../context/MessagingContext';
import { productNames } from '../constants/productLanguage';
import { useAppTheme } from '../context/AppThemeContext';

const Tab = createBottomTabNavigator<HomeTabParamList>();
const PlannerStack = createNativeStackNavigator<PlannerStackParamList>();
const MoreStack = createNativeStackNavigator<MoreStackParamList>();

type ShellNavigationFocus = {
  tab: keyof HomeTabParamList;
  leaf: string;
};

function getActiveLeafRouteName(route: any): string {
  let currentRoute = route;
  while (currentRoute?.state?.routes && typeof currentRoute.state.index === 'number') {
    currentRoute = currentRoute.state.routes[currentRoute.state.index];
  }
  return currentRoute?.name ?? route?.name ?? '';
}

function shouldShowGlobalTopBar(focus: ShellNavigationFocus): boolean {
  // Home is the household dashboard, where identity and global entry points
  // provide useful orientation. Every other destination owns its own heading
  // and context, so repeating the global bar only consumes useful workspace.
  return focus.tab === 'HomeTab';
}

function AttentionTopBarButton({ accessToken, householdId, navigation }: {
  accessToken: string | null;
  householdId: string | null;
  navigation: any;
}) {
  const [count, setCount] = useState(0);
  const requestSeq = useRef(0);

  const refreshCount = useCallback(() => {
    if (!GLOBAL_SURFACE_GATES_OFF.attention.enabled || !accessToken || !householdId) {
      setCount(0);
      return undefined;
    }
    const controller = new AbortController();
    const sequence = ++requestSeq.current;
    void fetchPlannerAttentionRequest({
      accessToken,
      limit: 100,
      signal: controller.signal,
      timeoutMs: 8000,
      contextScope: `planner-attention-badge:${householdId}`,
    }).then((response) => {
      if (sequence !== requestSeq.current || controller.signal.aborted) return;
      setCount(response.items.length);
    }).catch(() => {
      if (sequence !== requestSeq.current || controller.signal.aborted) return;
      setCount(0);
    });
    return () => controller.abort();
  }, [accessToken, householdId]);

  useEffect(() => refreshCount(), [refreshCount]);

  useFocusEffect(
    useCallback(() => refreshCount(), [refreshCount]),
  );

  if (!GLOBAL_SURFACE_GATES_OFF.attention.enabled) return null;

  return (
    <IconButton
      icon="notifications-outline"
      variant="plain"
      onPress={() => navigation.navigate('HomeTabs', {
        screen: 'PlannerTab',
        params: {
          screen: 'PlannerAttentionActivity',
          params: { source: 'planner', returnTo: 'previous' },
        },
      })}
      accessibilityLabel={count > 0 ? `Abrir Atención y actividad, ${count} asuntos sin resolver` : 'Abrir Atención y actividad'}
    >
      {count > 0 ? (
        <View style={styles.attentionBadge} accessibilityLabel={`${count} asuntos sin resolver`}>
          <AppText variant="micro" tone="inverse" weight="700" style={styles.attentionBadgeText}>
            {count > 99 ? '99+' : String(count)}
          </AppText>
        </View>
      ) : null}
    </IconButton>
  );
}

function TopBarActions({ accessToken, householdId, navigation }: {
  accessToken: string | null;
  householdId: string | null;
  navigation: any;
}) {
  const { unreadCount } = useMessaging();
  return (
    <View style={styles.topBarActions}>
      <IconButton
        icon="chatbubbles-outline"
        variant="plain"
        onPress={() => navigation.navigate('MessagesInbox')}
        testID="nav.messages"
        accessibilityLabel={unreadCount > 0 ? `Abrir Mensajes, ${unreadCount > 99 ? 'más de 99' : unreadCount} ${unreadCount === 1 ? 'mensaje sin leer' : 'mensajes sin leer'}` : 'Abrir Mensajes'}
      >
        {unreadCount > 0 ? (
          <View style={styles.messagesBadge} accessibilityLabel={`${unreadCount > 99 ? 'Más de 99' : unreadCount} ${unreadCount === 1 ? 'mensaje sin leer' : 'mensajes sin leer'}`}>
            <AppText variant="micro" tone="inverse" weight="700" style={styles.attentionBadgeText}>{unreadCount > 99 ? '99+' : String(unreadCount)}</AppText>
          </View>
        ) : null}
      </IconButton>
      <AttentionTopBarButton accessToken={accessToken} householdId={householdId} navigation={navigation} />
    </View>
  );
}

const MAIN_NAVIGATION_ITEMS: Record<keyof HomeTabParamList, FloatingNavigationItem> = {
  HomeTab: { id: 'HomeTab', icon: 'home-outline', iconSize: 22, label: productNames.home, accessibilityLabel: `Ir a ${productNames.home}`, testID: 'nav.home' },
  FamilyTab: { id: 'FamilyTab', icon: 'people-outline', iconSize: 23, label: 'Familia', accessibilityLabel: 'Ir a Familia', testID: 'nav.family' },
  QuickActionTab: { id: 'QuickActionTab', icon: 'add', iconSize: 26, label: 'Acciones rápidas', isAction: true, accessibilityLabel: 'Abrir acciones rápidas', testID: 'nav.quickAction' },
  PlannerTab: { id: 'PlannerTab', icon: 'calendar-outline', iconSize: 22, label: productNames.planner, accessibilityLabel: `Ir a ${productNames.planner}`, testID: 'nav.planner' },
  MoreTab: { id: 'MoreTab', icon: 'ellipsis-horizontal', iconSize: 24, iconOffsetY: -1, label: 'Más', accessibilityLabel: 'Abrir Más opciones', testID: 'nav.more' },
};

function HomeScreen() {
  const { currentRole, loading, reloading } = useHousehold();
  const { colors: themeColors } = useAppTheme();

  if (loading || reloading) {
    return (
      <View style={[styles.loadingContainer, { backgroundColor: themeColors.background.base }]}>
        <ActivityIndicator size="large" color={themeColors.brand} />
      </View>
    );
  }

  if (currentRole === 'coordinador')  return <HomeCoordinador />;
  if (currentRole === 'adulto')       return <HomeAdulto />;
  if (currentRole === 'adolescente')  return <HomeAdolescente />;
  if (currentRole === 'adulto_mayor') return <HomeAdultoMayor />;

  return <HomeCoordinador />;
}

function PlannerStackScreen() {
  return (
    <PlannerStack.Navigator initialRouteName="PlannerHome" screenOptions={{ headerShown: false }}>
      <PlannerStack.Screen name="PlannerHome" component={PlannerScreen} />
      <PlannerStack.Screen name="CreateTask" component={CreateTaskScreen} />
      <PlannerStack.Screen name="EditTask" component={EditTaskScreen} />
      <PlannerStack.Screen name="CreateEvent" component={CreateEventScreen} />
      <PlannerStack.Screen name="EditEvent" component={EditEventScreen} />
      <PlannerStack.Screen name="CreateGoal" component={CreateGoalScreen} />
      <PlannerStack.Screen name="EditGoal" component={PlannerPlanStructureEditScreen} />
      <PlannerStack.Screen name="GoalDetail" component={PlannerPlanDetailScreen} />
      <PlannerStack.Screen name="EditPlan" component={PlannerPlanStructureEditScreen} />
      <PlannerStack.Screen name="PlanList" component={PlannerPlanListScreen} />
      <PlannerStack.Screen name="PlanDetail" component={PlannerPlanDetailScreenV1} />
      <PlannerStack.Screen name="PlannerTrash" component={PlannerTrashScreen} />
      <PlannerStack.Screen name="PlannerPresetLibrary" component={PlannerPresetLibraryRoute} />
      <PlannerStack.Screen name="PlannerPresetDetail" component={PlannerPresetDetailRoute} />
      <PlannerStack.Screen name="PlannerPresetCreate" component={PlannerPresetCreateRoute} />
      <PlannerStack.Screen name="PlannerPresetEdit" component={PlannerPresetEditRoute} />
      <PlannerStack.Screen name="PlannerDraftRecovery" component={PlannerDraftRecoveryRoute} />
      <PlannerStack.Screen name="PlannerDraftResume" component={PlannerDraftResumeRoute} />
      <PlannerStack.Screen name="PlannerPresetDraftsTrash" component={PlannerPresetDraftsTrashRoute} />
      <PlannerStack.Screen name="PlannerSearch" component={PlannerSearchScreen} />
      <PlannerStack.Screen name="PlannerAttentionActivity" component={PlannerAttentionActivityScreen} />
      <PlannerStack.Screen name="TaskDetail" component={TaskDetailScreen} />
      <PlannerStack.Screen name="EventDetail" component={EventDetailScreen} />
      <PlannerStack.Screen name="Responsibilities" component={ResponsibilitiesScreen} />
      <PlannerStack.Screen name="ResponsibilityCreate" component={ResponsibilityFormScreen} />
      <PlannerStack.Screen name="ResponsibilityEdit" component={ResponsibilityFormScreen} />
      <PlannerStack.Screen name="ResponsibilityDetail" component={ResponsibilityDetailScreen} />
      <PlannerStack.Screen name="CreatePlan" component={PlannerPlanCreateScreen} />
    </PlannerStack.Navigator>
  );
}

function MoreStackScreen() {
  return (
    <MoreStack.Navigator screenOptions={{ headerShown: false }}>
      <MoreStack.Screen name="MoreHome" component={MoreScreen} />
      <MoreStack.Screen name="Assets" component={AssetsRootScreen} />
      <MoreStack.Screen name="AssetsArchived" component={AssetsArchivedScreen} />
      <MoreStack.Screen name="AssetsTrash" component={AssetsTrashScreen} />
      <MoreStack.Screen name="AssetsDetail" component={AssetDetailScreen} />
      <MoreStack.Screen name="AssetRecords" component={AssetRecordsScreen} />
      <MoreStack.Screen name="AssetCare" component={AssetCareScreen} />
      <MoreStack.Screen name="Family" component={FamilyScreen} />
      <MoreStack.Screen name="HomeCloud" component={HomeCloudScreen} />
      <MoreStack.Screen name="HomeCloudScanner" component={HomeCloudScannerScreen} />
      <MoreStack.Screen name="Inventory" component={InventarioScreen} />
      <MoreStack.Screen name="InventoryShopping" component={InventoryShoppingListScreen} />
      <MoreStack.Screen name="InventoryPurchase" component={InventoryPurchaseScreen} />
      <MoreStack.Screen name="Finance" component={FinanceScreen} />
      <MoreStack.Screen name="FinanceAccounts" component={FinanceAccountsScreen} />
      <MoreStack.Screen name="FinancePapelera" component={FinancePapeleraScreen} />
      <MoreStack.Screen name="FinancePoolManagement" component={FinancePoolManagementScreen} />
      <MoreStack.Screen name="FinanceSpendingLimitsManagement" component={FinanceSpendingLimitsManagementScreen} />
      <MoreStack.Screen name="FinanceCategoryManagement" component={FinanceCategoryManagementScreen} />
      <MoreStack.Screen name="FinanceAnalysisDetail" component={FinanceAnalysisDetailScreen} />
      <MoreStack.Screen name="Presence" component={PresenceScreen} />
      <MoreStack.Screen name="Homi" component={HomiScreen} options={{ headerShown: false }} />
    </MoreStack.Navigator>
  );
}

function QuickActionPlaceholder() {
  return null;
}

function MainFloatingTabBar({ state, navigation }: BottomTabBarProps) {
  const { openActions } = usePlannerSheet();
  const insets = useSafeAreaInsets();
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const activeRoute = state.routes[state.index];
  const activeId = activeRoute.name === 'QuickActionTab' ? undefined : activeRoute.name;
  const navigationItems = useMemo(
    () => state.routes
      .filter((route) => route.name !== 'QuickActionTab')
      .map((route) => MAIN_NAVIGATION_ITEMS[route.name as keyof HomeTabParamList]),
    [state.routes],
  );

  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const showSubscription = Keyboard.addListener(showEvent, () => setKeyboardVisible(true));
    const hideSubscription = Keyboard.addListener(hideEvent, () => setKeyboardVisible(false));

    return () => {
      showSubscription.remove();
      hideSubscription.remove();
    };
  }, []);

  const handleSelect = useCallback((item: FloatingNavigationItem) => {
    if (item.id === 'QuickActionTab') {
      openActions();
      return;
    }

    const route = state.routes.find((candidate) => candidate.name === item.id);
    if (!route) return;

    const event = navigation.emit({
      type: 'tabPress',
      target: route.key,
      canPreventDefault: true,
    });

    const isAlreadyFocused = state.routes[state.index]?.key === route.key;
    if (!event.defaultPrevented && !isAlreadyFocused) {
      navigation.navigate(route.name);
    }
  }, [navigation, openActions, state.index, state.routes]);

  if (keyboardVisible) return null;

  return (
    <View
      pointerEvents="box-none"
      style={[
        styles.floatingTabBarShell,
        { paddingBottom: insets.bottom + spacing[2] },
      ]}
    >
      <FloatingNavigationBar
        items={navigationItems}
        activeId={activeId}
        onSelect={handleSelect}
        variant="main"
        display="icon-only"
        appearance="auto"
        style={styles.mainNavigationBar}
      />
    </View>
  );
}

export function HomeTabNavigator() {
  const { colors: themeColors } = useAppTheme();
  const { session, authMe } = useAuth();
  const { currentHousehold } = useHousehold();
  const navigation = useNavigation<any>();
  
  const [showHouseholdSwitcher, setShowHouseholdSwitcher] = useState(false);
  const [showAccountSheet, setShowAccountSheet] = useState(false);
  const [navigationFocus, setNavigationFocus] = useState<ShellNavigationFocus>({
    tab: 'HomeTab',
    leaf: 'HomeTab',
  });
  const activeTabRef = useRef<SettingsOriginTab>(DEFAULT_SETTINGS_ORIGIN);

  const personName = authMe?.person?.display_name ?? 'Usuario';
  const personAvatarUrl = authMe?.person?.avatar_url ?? null;
  const householdName = authMe?.active_household?.name ?? 'Hogar';
  const householdRole = authMe?.memberships?.find(m => m.household_id === authMe?.active_household?.id)?.role ?? 'adult';

  const handleAvatarPress = useCallback(() => {
    setShowAccountSheet(true);
  }, []);

  const handleOpenProfile = useCallback(() => {
    navigation.navigate('ProfileScreen');
  }, [navigation]);

  const handleOpenNotifications = useCallback(() => {
    navigation.navigate('NotificationSettings', { originTab: activeTabRef.current });
  }, [navigation]);

  const handleOpenSecurity = useCallback(() => {
    navigation.navigate('SecuritySettings', { originTab: activeTabRef.current });
  }, [navigation]);

  const handleHouseholdPress = useCallback(() => {
    setShowHouseholdSwitcher(true);
  }, []);

  const handleTabStateChange = useCallback((event: any) => {
    const tabState = event.data.state;
    const activeRoute = tabState?.routes?.[tabState.index];
    const activeTab = activeRoute?.name as keyof HomeTabParamList | undefined;
    if (!activeTab) return;

    if (activeTab === 'HomeTab' || activeTab === 'FamilyTab' || activeTab === 'PlannerTab' || activeTab === 'MoreTab') {
      activeTabRef.current = activeTab;
    }

    const nextFocus: ShellNavigationFocus = {
      tab: activeTab,
      leaf: getActiveLeafRouteName(activeRoute),
    };
    setNavigationFocus((current) => (
      current.tab === nextFocus.tab && current.leaf === nextFocus.leaf ? current : nextFocus
    ));
  }, []);

  // S2: The Reliability runtime Owner is mounted ONCE in `PrivateNavigator`
  // (AppNavigator) above this `HomeTabNavigator`, so it covers HomeTabs,
  // Quick Actions, Profile and the fallback screens. It survives tab screen
  // unmounts (e.g. navigating away from PlannerTab) and does NOT depend on
  // PlannerScreen mounting. We deliberately do NOT key anything by household
  // here: the Owner detects household changes itself.

  return (
    <View style={[styles.container, { backgroundColor: themeColors.background.base }]}>
      {shouldShowGlobalTopBar(navigationFocus) ? (
        <AppTopBar
          personName={personName}
          personAvatarUrl={personAvatarUrl}
          avatarTestID="account.menu.open"
          householdName={householdName}
          householdRole={householdRole}
          onAvatarPress={handleAvatarPress}
          onHouseholdPress={handleHouseholdPress}
          rightSlot={(
            <TopBarActions
              accessToken={session?.access_token ?? null}
              householdId={currentHousehold?.id ?? authMe?.active_household?.id ?? null}
              navigation={navigation}
            />
          )}
        />
      ) : null}

      <PlannerDeepLinkProvider>
        <PlannerSheetProvider>
        <Tab.Navigator
          tabBar={(props) => <MainFloatingTabBar {...props} />}
          screenListeners={{
            state: handleTabStateChange,
          }}
          screenOptions={{
            headerShown: false,
            tabBarShowLabel: false,
            tabBarHideOnKeyboard: true,
          }}
        >
          <Tab.Screen
            name="HomeTab"
            component={HomeScreen}
            options={{
              tabBarAccessibilityLabel: productNames.home,
            }}
          />

          <Tab.Screen
            name="FamilyTab"
            component={FamilyScreen}
            options={{
              tabBarAccessibilityLabel: 'Familia',
            }}
          />

          <Tab.Screen
            name="QuickActionTab"
            component={QuickActionPlaceholder}
            listeners={{
              tabPress: (event) => {
                event.preventDefault();
              },
            }}
            options={{
              tabBarAccessibilityLabel: 'Acciones rápidas',
            }}
          />

          <Tab.Screen
            name="PlannerTab"
            component={PlannerStackScreen}
            options={{
              tabBarAccessibilityLabel: productNames.planner,
            }}
          />

          <Tab.Screen
            name="MoreTab"
            component={MoreStackScreen}
            options={{
              tabBarAccessibilityLabel: 'Más',
            }}
          />
        </Tab.Navigator>

        {/* M3: Single sheet host — replaces both QuickActionSheet Modal and
            the legacy compat-bridge Modal in PlannerScreen. */}
        <PlannerSheetHost />
      </PlannerSheetProvider>
      </PlannerDeepLinkProvider>

      <HouseholdSwitcherSheet
        visible={showHouseholdSwitcher}
        onRequestClose={() => setShowHouseholdSwitcher(false)}
        accessToken={session?.access_token ?? null}
      />
      <AccountSheet
        visible={showAccountSheet}
        onRequestClose={() => setShowAccountSheet(false)}
        onOpenProfile={handleOpenProfile}
        onOpenNotifications={handleOpenNotifications}
        onOpenSecurity={handleOpenSecurity}
      />
    </View>
  );
}



const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background.base,
  },
  floatingTabBarShell: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 10,
    // The Figma shell keeps the navigation as a deliberate floating control,
    // not a near-full-width footer. The inset is responsive and preserves
    // the existing safe-area padding below.
    paddingHorizontal: spacing[6],
    alignItems: 'center',
  },
  mainNavigationBar: {
    maxWidth: 520,
  },
  topBarActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[1],
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: colors.background.base,
    alignItems: 'center',
    justifyContent: 'center',
  },
  attentionBadge: {
    position: 'absolute',
    top: 4,
    right: 2,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
    backgroundColor: colors.brand,
  },
  attentionBadgeText: {
    fontSize: 10,
  },
  messagesBadge: {
    position: 'absolute',
    top: 2,
    right: 0,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
    backgroundColor: colors.brand,
  },
});
