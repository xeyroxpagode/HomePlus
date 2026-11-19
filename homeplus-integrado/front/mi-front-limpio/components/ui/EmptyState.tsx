import React from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';

import { radius, spacing } from '../../constants/theme';
import { useAppTheme } from '../../context/AppThemeContext';
import { AppButton } from './AppButton';
import { AppText } from './AppText';

export type EmptyStateProps = {
  title: string;
  description?: string;
  variant?: 'default' | 'compact';
  illustration?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  style?: StyleProp<ViewStyle>;
};

export function EmptyState({
  title,
  description,
  variant = 'default',
  illustration,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
  style,
}: EmptyStateProps) {
  const { colors } = useAppTheme();
  const compact = variant === 'compact';
  return (
    <View
      style={[
        {
          alignItems: compact ? 'flex-start' : 'center',
          justifyContent: 'center',
          padding: compact ? 0 : spacing[6],
          paddingVertical: compact ? spacing[2] : spacing[6],
          gap: compact ? spacing[2] : spacing[4],
        },
        style,
      ]}
    >
      {illustration ? (
        <View
          style={{
            minHeight: compact ? 24 : 72,
            minWidth: compact ? 24 : 72,
            borderRadius: radius.xxl,
            backgroundColor: compact ? undefined : colors.sand[50],
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {illustration}
        </View>
      ) : null}
      <View style={{ gap: spacing[2], alignItems: compact ? 'flex-start' : 'center' }}>
        <AppText variant={compact ? 'bodySmall' : 'title3'} tone={compact ? 'secondary' : 'primary'} align={compact ? 'left' : 'center'}>
          {title}
        </AppText>
        {description ? <AppText variant="bodySmall" tone="secondary" align={compact ? 'left' : 'center'}>
          {description}
        </AppText> : null}
      </View>
      {actionLabel && onAction ? (
        <AppButton title={actionLabel} onPress={onAction} accessibilityLabel={actionLabel} />
      ) : null}
      {secondaryActionLabel && onSecondaryAction ? (
        <AppButton
          title={secondaryActionLabel}
          variant="ghost"
          onPress={onSecondaryAction}
          accessibilityLabel={secondaryActionLabel}
        />
      ) : null}
    </View>
  );
}
