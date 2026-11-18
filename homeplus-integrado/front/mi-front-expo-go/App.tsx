import React from 'react';
import { View } from 'react-native';
import { NavigationContainer, type LinkingOptions } from '@react-navigation/native';
import { useFonts } from 'expo-font';
import {
  Manrope_400Regular,
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
} from '@expo-google-fonts/manrope';
import * as Linking from 'expo-linking';
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
import { AppThemeProvider } from './context/AppThemeContext';

registerLifecycleHandlers();

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
                      <NavigationContainer linking={linking}>
                        {/* Stable automation anchor after fonts and providers are ready. */}
                        <View testID="app.shell" style={{ flex: 1 }}>
                          <AppNavigator />
                        </View>
                      </NavigationContainer>
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
