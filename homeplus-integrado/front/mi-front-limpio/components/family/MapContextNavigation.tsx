import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { HomePlusIcon, type HomePlusIconName } from '../../constants/icons';
import { radius, spacing, touchTargets } from '../../constants/theme';
import { AppText, InteractivePressable } from '../ui';
import type { MapContextCardMode } from './MapContextCard';

export const mapContextActionsHeight = 44;

type MapContextNavigationItem = {
  id: MapContextCardMode;
  icon: HomePlusIconName;
  label: string;
};

type MapContextNavigationProps = {
  activeItem: MapContextCardMode | null;
  onSelect: (item: MapContextCardMode) => void;
};

const ITEMS: readonly MapContextNavigationItem[] = [
  { id: 'members', icon: 'people-outline', label: 'Integrantes' },
  { id: 'places', icon: 'location-outline', label: 'Lugares' },
];

/** Compact map controls; these act on the map instead of becoming a second navbar. */
export function MapContextActions({ activeItem, onSelect }: MapContextNavigationProps) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  return (
    <View accessibilityRole="toolbar" style={styles.actions}>
      {ITEMS.map((item) => {
        const active = item.id === activeItem;
        return (
          <InteractivePressable
            key={item.id}
            accessibilityRole="button"
            accessibilityLabel={`Mostrar ${item.label.toLowerCase()} en el mapa`}
            accessibilityState={{ selected: active }}
            onPress={() => onSelect(item.id)}
            haptic="none"
            pressScale={0.98}
            style={[styles.action, active ? styles.actionActive : null]}
          >
            <HomePlusIcon name={item.icon} size={19} color={active ? colors.brandPressed : colors.text.secondary} />
            <AppText variant="caption" weight="700" style={active ? styles.activeLabel : styles.inactiveLabel}>
              {item.label}
            </AppText>
          </InteractivePressable>
        );
      })}
    </View>
  );
}

/** Source-compatible aliases for older consumers. */
export const MapContextNavigation = MapContextActions;
export const mapContextNavigationHeight = mapContextActionsHeight;



function createStylesForTheme({ colors, shadows }: Pick<AppResolvedTheme, 'colors' | 'shadows'>) {
  return StyleSheet.create({
  actions: {
    height: mapContextActionsHeight,
    alignSelf: 'flex-end',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  action: {
    minWidth: touchTargets.normal,
    minHeight: touchTargets.normal,
    paddingHorizontal: spacing[3],
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: spacing[2],
    borderRadius: radius.full,
    backgroundColor: colors.surface.glass,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    ...shadows.shadow2,
  },
  actionActive: {
    backgroundColor: colors.brandSoft,
    borderColor: colors.terracotta[100],
  },
  activeLabel: { color: colors.brandPressed },
  inactiveLabel: { color: colors.text.secondary },
});
}
