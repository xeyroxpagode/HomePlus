import React from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { spacing } from '../../constants/theme';
import { AppText } from './AppText';

type AppPageHeaderProps = {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
};

/** Shared compact page heading for primary StandardShell destinations. */
export function AppPageHeader({ title, subtitle, action, style }: AppPageHeaderProps) {
  return (
    <View style={[styles.root, style]}>
      <View style={styles.copy}>
        <AppText variant="title1" weight="600" accessibilityRole="header">{title}</AppText>
        {subtitle ? <AppText variant="bodySmall" tone="secondary">{subtitle}</AppText> : null}
      </View>
      {action ? <View style={styles.action}>{action}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
  },
  copy: {
    flex: 1,
    minWidth: 0,
    gap: spacing[1],
  },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[1],
  },
});
