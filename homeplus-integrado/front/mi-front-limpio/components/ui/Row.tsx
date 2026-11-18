import React from 'react';
import { View, type PressableProps, type StyleProp, type ViewStyle } from 'react-native';
import { radius, spacing } from '../../constants/theme';
import { useAppTheme } from '../../context/AppThemeContext';
import { AppText } from './AppText';
import { InteractivePressable } from './InteractivePressable';

export type RowProps = Omit<PressableProps, 'children' | 'style'> & {
  title?: string;
  subtitle?: string;
  leftSlot?: React.ReactNode;
  rightSlot?: React.ReactNode;
  /** Composed domain content retains its own actions and semantics. */
  children?: React.ReactNode;
  variant?: 'plain' | 'card';
  divider?: boolean;
  titleNumberOfLines?: number;
  style?: StyleProp<ViewStyle>;
};

/** Shared task-density row. Money, stock and roles remain domain-owned. */
export function Row({ title, subtitle, leftSlot, rightSlot, children, variant = 'plain',
  divider = true, titleNumberOfLines = 2, onPress, disabled, accessibilityLabel,
  accessibilityState, style, ...props }: RowProps) {
  const { colors } = useAppTheme();
  const geometry: StyleProp<ViewStyle> = [{
    minHeight: 72,
    flexDirection: 'row', alignItems: 'center', gap: spacing[3],
    paddingVertical: spacing[3],
    borderBottomWidth: divider ? 1 : 0, borderBottomColor: colors.border.subtle,
  }, variant === 'card' ? {
    paddingHorizontal: spacing[3], marginBottom: spacing[2],
    borderWidth: 1, borderColor: colors.border.subtle,
    borderRadius: radius.lg, backgroundColor: colors.surface.soft,
  } : null, style];
  const content = children ?? <>
    {leftSlot}
    <View style={{ flex: 1, minWidth: 0, gap: spacing[1] }}>
      <AppText variant="bodySmall" weight="600" tone={disabled ? "muted" : "primary"} numberOfLines={titleNumberOfLines}>{title}</AppText>
      {subtitle ? <AppText variant="caption" tone={disabled ? "muted" : "tertiary"} numberOfLines={2}>{subtitle}</AppText> : null}
    </View>
    {rightSlot}
  </>;
  if (!onPress) return <View style={geometry} {...props}>{content}</View>;
  return <InteractivePressable {...props} accessibilityRole="button"
    accessibilityLabel={accessibilityLabel ?? (subtitle ? `${title}. ${subtitle}` : title)}
    accessibilityState={{ ...accessibilityState, disabled: Boolean(disabled), busy: accessibilityState?.busy }}
    disabled={disabled} onPress={onPress} haptic="none" pressScale={1} pressedOpacity={0.92}
    style={geometry}>{content}</InteractivePressable>;
}
