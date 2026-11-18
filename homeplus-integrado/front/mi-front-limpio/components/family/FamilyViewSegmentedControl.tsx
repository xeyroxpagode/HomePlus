
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React from 'react';
import { StyleSheet, type StyleProp, type ViewStyle } from 'react-native';

import { SegmentedControl } from '../ui';


export type FamilyViewTab = 'people' | 'map';

type FamilyViewSegmentedControlProps = {
  activeTab: FamilyViewTab;
  onChange: (tab: FamilyViewTab) => void;
  style?: StyleProp<ViewStyle>;
};

/** Shared view switcher for the Family people and map experiences. */
export function FamilyViewSegmentedControl({
  activeTab,
  onChange,
  style,
}: FamilyViewSegmentedControlProps) {
  const styles = useThemeStyles(createStylesForTheme);

  return (
    <SegmentedControl
      selectionMode="single"
      value={activeTab}
      onChange={onChange}
      options={[
        { value: 'people', label: 'Personas' },
        { value: 'map', label: 'Mapa' },
      ]}
      size="compact"
      style={[styles.control, style]}
    />
  );
}



function createStylesForTheme({ colors, shadows }: Pick<AppResolvedTheme, 'colors' | 'shadows'>) {
  return StyleSheet.create({
  control: {
    alignSelf: 'center',
    width: '58%',
    minWidth: 188,
    maxWidth: 236,
    backgroundColor: colors.surface.glass,
    ...shadows.shadow2,
  },
});
}
