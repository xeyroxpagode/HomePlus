import React from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { spacing, touchTargets } from '../../constants/theme';
import { AppText } from './AppText';

type AppPageHeaderProps = {
  title: string;
  subtitle?: string;
  leading?: React.ReactNode;
  action?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
};

/** Shared compact page heading for primary StandardShell destinations. */
export function AppPageHeader({ title, subtitle, leading, action, style }: AppPageHeaderProps) {
  return (
    <View style={[styles.root, style]}>
      <View style={styles.row}>
        <View style={styles.leading}>{leading}</View>
        <View style={styles.copy}>
          <AppText variant="title1" weight="600" align="center" accessibilityRole="header">{title}</AppText>
        </View>
        <View style={styles.action}>{action}</View>
      </View>
      {subtitle ? <AppText variant="bodySmall" tone="secondary" align="center">{subtitle}</AppText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: spacing[1] },
  row: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
  copy: {
    flex: 3,
    minWidth: 0,
    gap: spacing[1],
  },
  leading: {
    flex: 1,
    minWidth: touchTargets.normal,
    minHeight: touchTargets.normal,
    flexDirection: 'row',
    alignItems: 'center',
  },
  action: {
    flex: 1,
    minWidth: touchTargets.normal,
    minHeight: touchTargets.normal,
    justifyContent: 'flex-end',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[1],
  },
});
