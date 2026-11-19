import React from 'react';
import { StyleSheet, View, useWindowDimensions, type StyleProp, type ViewStyle } from 'react-native';

import { spacing, touchTargets } from '../../constants/theme';
import { AppText } from './AppText';

type AppPageHeaderProps = {
  title: string;
  subtitle?: string;
  leading?: React.ReactNode;
  action?: React.ReactNode;
  singleLineTitle?: boolean;
  style?: StyleProp<ViewStyle>;
};

/** Shared compact page heading for primary StandardShell destinations. */
export function AppPageHeader({ title, subtitle, leading, action, singleLineTitle = false, style }: AppPageHeaderProps) {
  const { width, fontScale } = useWindowDimensions();
  // At accessibility sizes, give the title its own row rather than clipping it
  // or reducing the user's chosen font scale to fit beside the controls.
  const stacked = singleLineTitle && (width < 360 || fontScale > 1.3);
  const heading = (
    <AppText variant="title1" weight="600" align="center" accessibilityRole="header"
      numberOfLines={singleLineTitle ? 1 : undefined}
      adjustsFontSizeToFit={singleLineTitle} minimumFontScale={0.8}>
      {title}
    </AppText>
  );
  return (
    <View style={[styles.root, style]}>
      {stacked ? heading : null}
      <View style={styles.row}>
        <View style={styles.leading}>{leading}</View>
        <View style={styles.copy}>
          {stacked ? null : heading}
        </View>
        <View style={styles.action}>{action}</View>
      </View>
      {subtitle ? <AppText variant="bodySmall" tone="secondary" align="center">{subtitle}</AppText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { alignSelf: 'stretch', gap: spacing[1] },
  row: {
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
  leading: {
    flexShrink: 0,
    minWidth: touchTargets.normal,
    minHeight: touchTargets.normal,
    flexDirection: 'row',
    alignItems: 'center',
  },
  action: {
    flexShrink: 0,
    minWidth: touchTargets.normal,
    minHeight: touchTargets.normal,
    justifyContent: 'flex-end',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[1],
  },
});
