import React from 'react';
import { StyleSheet } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import { AppScreen } from '../../components/ui';
import { spacing } from '../../constants/theme';
import { HomePlannerSections } from './HomePlannerSections';
import { HomeWelcomeHeader } from './HomeWelcomeHeader';

// ─── Main screen ─────────────────────────────────────────────────────────────

export const HomeCoordinador = () => {
  const { user } = useAuth();
  const { currentHousehold } = useHousehold();

  const firstName = user?.user_metadata?.nombre?.split(' ')[0] ?? 'Coordinador';

  return (
    <AppScreen scroll bottomInset="tab" safeAreaEdges={['left', 'right', 'bottom']} contentContainerStyle={styles.content}>

        <HomeWelcomeHeader firstName={firstName} householdName={currentHousehold?.nombre} />

        <HomePlannerSections />
    </AppScreen>
  );
};

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  content: { paddingTop: spacing[4] },

});
