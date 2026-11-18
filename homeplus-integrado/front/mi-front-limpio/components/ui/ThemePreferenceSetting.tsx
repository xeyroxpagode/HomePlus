import React from 'react';
import { View } from 'react-native';

import { useAppThemePreference } from '../../context/AppThemeContext';
import type { ThemePreference } from '../../constants/theme';
import { AppCard } from './AppCard';
import { AppText } from './AppText';
import { SegmentedControl } from './SegmentedControl';

const options: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Automático' },
  { value: 'light', label: 'Claro' },
  { value: 'dark', label: 'Oscuro' },
];

export function ThemePreferenceSetting() {
  const { preference, setPreference } = useAppThemePreference();

  return (
    <AppCard variant="default" padding="default">
      <View style={{ gap: 12 }}>
        <AppText variant="bodySmall" weight="700">Apariencia</AppText>
        <SegmentedControl
          options={options}
          value={preference}
          onChange={setPreference}
          accessibilityLabel="Apariencia de HomePlus"
          testID="settings.theme.preference"
        />
        <AppText variant="caption" tone="secondary">
          Automático sigue la configuración de tu teléfono.
        </AppText>
      </View>
    </AppCard>
  );
}
