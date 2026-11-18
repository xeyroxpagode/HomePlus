import React from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';

import { layout } from '../../constants/theme';
import { AppText } from './AppText';

type AppSectionProps = {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  contentStyle?: StyleProp<ViewStyle>;
};

/** Consistent heading, alignment and vertical rhythm for product sections. */
export function AppSection({ title, subtitle, action, children, style, contentStyle }: AppSectionProps) {
  const hasHeader = Boolean(title || subtitle || action);

  return (
    <View style={[{ width: '100%', gap: layout.stack.content }, style]}>
      {hasHeader ? (
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: layout.stack.component }}>
          <View style={{ flex: 1, gap: layout.stack.tight }}>
            {title ? <AppText variant="title2">{title}</AppText> : null}
            {subtitle ? <AppText variant="bodySmall" tone="secondary">{subtitle}</AppText> : null}
          </View>
          {action}
        </View>
      ) : null}
      <View style={[{ width: '100%', gap: layout.stack.component }, contentStyle]}>{children}</View>
    </View>
  );
}
