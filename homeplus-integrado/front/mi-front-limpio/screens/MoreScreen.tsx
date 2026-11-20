import React from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { AppScreen } from '../components/ui/AppScreen';
import { AppText } from '../components/ui/AppText';
import { AppPageHeader } from '../components/ui/AppPageHeader';
import { InteractivePressable } from '../components/ui/InteractivePressable';
import { HomePlusIcon, type HomePlusIconName } from '../constants/icons';
import { iconSizes, layout, touchTargets } from '../constants/theme';
import { useAppTheme } from '../context/AppThemeContext';
import { productNames } from '../constants/productLanguage';

const MODULES = [
  {
    id: 'assets',
    label: productNames.assets,
    accessibilityLabel: "Objetos del hogar",
    icon: 'cube-outline' as HomePlusIconName,
    screen: 'Assets' as const,
    isDemo: false,
  },
  {
    id: 'homecloud',
    label: productNames.files,
    icon: 'cloud-outline' as HomePlusIconName,
    screen: 'HomeCloud' as const,
    isDemo: false,
  },
  {
    id: 'feed',
    label: 'Actividad',
    accessibilityLabel: 'Actividad del hogar',
    icon: 'chatbubbles' as HomePlusIconName,
    screen: 'FeedFamiliar' as const,
    isDemo: true,
  },
  {
    id: 'finance',
    label: 'Finanzas',
    icon: 'wallet' as HomePlusIconName,
    screen: 'Finance' as const,
    isDemo: false,
  },
  {
    id: 'inventory',
    label: 'Inventario',
    icon: 'archive' as HomePlusIconName,
    screen: 'Inventory' as const,
    isDemo: false,
  },
  {
    id: 'homi',
    label: productNames.homi,
    accessibilityLabel: productNames.homi,
    icon: 'sparkles' as HomePlusIconName,
    screen: 'Homi' as const,
    isDemo: false,
  },
];

type ModuleTileProps = {
  module: (typeof MODULES)[number];
  singleColumn: boolean;
  onPress: () => void;
};

function ModuleTile({ module, singleColumn, onPress }: ModuleTileProps) {
  const theme = useAppTheme();
  const styles = createStyles(theme);
  const accessibleName = 'accessibilityLabel' in module ? module.accessibilityLabel : module.label;

  return (
    <InteractivePressable
      onPress={onPress}
      style={[styles.moduleTile, singleColumn ? styles.moduleTileSingle : null]}
      accessibilityRole="button"
      accessibilityLabel={`Abrir ${accessibleName}${module.isDemo ? ', demostración' : ''}`}
      testID={`more.module.${module.id}`}
      haptic="none"
      pressScale={1}
      pressedOpacity={0.92}
    >
      <View style={styles.moduleIcon} importantForAccessibility="no-hide-descendants">
        <HomePlusIcon name={module.icon} size={iconSizes.navbar} color={theme.colors.terracotta[600]} />
      </View>
      <View style={styles.moduleText}>
        <AppText variant="bodySmall" weight="700" style={styles.moduleLabel}>
          {module.label}
        </AppText>
        {module.isDemo ? (
          <AppText variant="caption" tone="tertiary" weight="600">Demo</AppText>
        ) : null}
      </View>
    </InteractivePressable>
  );
}

export function MoreScreen() {
  const navigation = useNavigation<any>();
  const { width, fontScale } = useWindowDimensions();
  const theme = useAppTheme();
  const styles = createStyles(theme);
  // Keep the approved two-column spatial memory at common text sizes. At an
  // actually constrained width or accessibility scale, legibility wins.
  const singleColumn = width / fontScale < 360 || fontScale >= 1.6;

  const handleModulePress = (screen: string | null | undefined) => {
    if (!screen) {
      return;
    }
    navigation.navigate(screen);
  };

  return (
    <AppScreen scroll bottomInset="tab" background="base" contentContainerStyle={styles.content}
      scrollProps={{ removeClippedSubviews: false }}>
      <AppPageHeader title="Más" subtitle="Accesos y herramientas del hogar" />

      <View style={styles.moduleSection}>
        <AppText variant="caption" tone="tertiary" weight="700" style={styles.sectionLabel}>
          HOMEPLUS
        </AppText>
        <View style={styles.modules} accessibilityRole="list">
          {MODULES.map((module) => (
            <ModuleTile
              key={module.id}
              module={module}
              singleColumn={singleColumn}
              onPress={() => handleModulePress(module.screen)}
            />
          ))}
        </View>
      </View>
    </AppScreen>
  );
}

function createStyles(theme: ReturnType<typeof useAppTheme>) {
  const { colors, radius, spacing } = theme;
  return StyleSheet.create({
  content: { gap: layout.stack.section, paddingTop: layout.screen.topPadding },
  moduleSection: {
    gap: layout.stack.related,
  },
  sectionLabel: {
    paddingHorizontal: spacing[1],
    letterSpacing: 0.7,
  },
  modules: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing[3],
  },
  moduleTile: {
    flexGrow: 0,
    flexBasis: '48%',
    width: '48%',
    maxWidth: '48%',
    minWidth: 0,
    minHeight: touchTargets.normal + spacing[8],
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: spacing[3],
    paddingHorizontal: spacing[3],
    paddingVertical: spacing[3],
    borderWidth: 1,
    borderColor: colors.border.subtle,
    borderRadius: radius.lg,
    backgroundColor: colors.surface.card,
  },
  moduleTileSingle: {
    flexBasis: '100%',
    width: '100%',
    maxWidth: '100%',
  },
  moduleIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.brandSoft,
  },
  moduleText: {
    flex: 1,
    minWidth: 0,
    justifyContent: 'center',
    gap: spacing[1],
  },
  moduleLabel: { minWidth: 0 },
  });
}
