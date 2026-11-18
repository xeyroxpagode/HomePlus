import React, { useEffect, useMemo } from 'react';
import { View } from 'react-native';
import { DarkTheme, DefaultTheme, NavigationContainer, type LinkingOptions } from '@react-navigation/native';
import { useFonts } from 'expo-font';
import {
  Manrope_400Regular,
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
} from '@expo-google-fonts/manrope';
import * as Linking from 'expo-linking';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthProvider } from './context/AuthContext';
import { ExperienceProvider } from './context/ExperienceContext';
import { HouseholdProvider } from './context/HouseholdContext';
import { AppRefreshProvider } from './context/AppRefreshContext';
import { PlannerTaskRealtimeBridge } from './context/PlannerTaskRealtimeBridge';
import { AppNavigator } from './navigation/AppNavigator';
import type { RootStackParamList } from './navigation/types';
import { registerLifecycleHandlers } from './services/registerLifecycleHandlers';
import { FeatureFlagsProvider } from './context/FeatureFlagsContext';
import { AuthLoadingScreen } from './screens/AuthLoading';
import { AppThemeProvider, useAppTheme } from './context/AppThemeContext';

registerLifecycleHandlers();
// Keep the native launch surface until fonts and the persisted theme are ready.
void SplashScreen.preventAutoHideAsync();

const linking: LinkingOptions<RootStackParamList> = {
  prefixes: [Linking.createURL('/')],
  config: {
    screens: {
      P00Splash: '',
      Login: 'login',
      P01Registro: 'registro',
      ForgotPassword: 'forgot-password',
      UpdatePassword: 'auth/callback',
      P02CrearGrupo: 'crear-grupo',
      P03InvitarPersonas: 'invitar/:householdId',
      HomeTabs: {
        path: 'home',
        screens: {
          PlannerTab: {
            path: 'planner',
            screens: {
              PlannerHome: '',
              // Deep-link paths for detail screens under the PlannerTab stack.
              // Entity IDs are validated as UUIDs before any request.
              // Household is resolved server-side from the authenticated context.
              // An entity belonging to another household results in deny/not-found.
              TaskDetail: 'tasks/:entityId',
              EventDetail: 'events/:entityId',
              GoalDetail: 'goals/:entityId',
              PlannerSearch: 'search',
            },
          },
        },
      },
      JoinHousehold: 'join',
    },
  },
};

function ThemedNavigation() {
  const { colors, resolvedScheme } = useAppTheme();
  useEffect(() => {
    void SplashScreen.hideAsync();
  }, []);
  const navigationTheme = useMemo(() => ({
    ...(resolvedScheme === 'dark' ? DarkTheme : DefaultTheme),
    colors: {
      ...(resolvedScheme === 'dark' ? DarkTheme.colors : DefaultTheme.colors),
      primary: colors.brand,
      background: colors.background.base,
      card: colors.surface.card,
      text: colors.text.primary,
      border: colors.border.default,
      notification: colors.danger.base,
    },
  }), [colors, resolvedScheme]);

  return (
    <NavigationContainer linking={linking} theme={navigationTheme}>
      <View testID="app.shell" style={{ flex: 1, backgroundColor: colors.background.base }}>
        <AppNavigator />
      </View>
    </NavigationContainer>
  );
}

export default function App() {
  const [fontsLoaded] = useFonts({
    Manrope_400Regular,
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
    Manrope_800ExtraBold,
  });

  return (
    <SafeAreaProvider>
      <AppThemeProvider>
        {!fontsLoaded ? (
          <AuthLoadingScreen />
        ) : (
          <AuthProvider>
            <ExperienceProvider>
              <HouseholdProvider>
                <FeatureFlagsProvider>
                  <AppRefreshProvider>
                    <PlannerTaskRealtimeBridge>
                      <ThemedNavigation />
                    </PlannerTaskRealtimeBridge>
                  </AppRefreshProvider>
                </FeatureFlagsProvider>
              </HouseholdProvider>
            </ExperienceProvider>
          </AuthProvider>
        )}
      </AppThemeProvider>
    </SafeAreaProvider>
  );
}
