import React from 'react';
import { Platform, Text, type TextProps, type TextStyle } from 'react-native';

import { typography, type ColorTokens, type TypographyVariant } from '../../constants/theme';
import { useAppTheme } from '../../context/AppThemeContext';

export type AppTextTone =
  | 'primary'
  | 'secondary'
  | 'tertiary'
  | 'muted'
  | 'brand'
  | 'inverse'
  | 'danger'
  | 'warning'
  | 'success'
  | 'info';

export type AppTextProps = TextProps & {
  variant?: TypographyVariant;
  tone?: AppTextTone;
  align?: TextStyle['textAlign'];
  weight?: TextStyle['fontWeight'];
};

function toneColors(colors: ColorTokens): Record<AppTextTone, string> {
  return {
    primary: colors.text.primary,
    secondary: colors.text.secondary,
    tertiary: colors.text.tertiary,
    muted: colors.text.muted,
    brand: colors.brand,
    inverse: colors.text.inverse,
    danger: colors.danger.text,
    warning: colors.warning.text,
    success: colors.success.text,
    info: colors.info.text,
  };
}

function fontFamilyForWeight(weight?: TextStyle['fontWeight']) {
  // Native system type is deliberately used across the product: San Francisco
  // on iOS gives HomePlus the compact, calm reading rhythm of the approved UI;
  // Android keeps its platform-native sans-serif equivalent.
  if (Platform.OS === 'android') {
    const numericWeight = typeof weight === 'string' ? Number(weight) : weight;
    return { fontFamily: numericWeight && numericWeight >= 600 ? 'sans-serif-medium' : 'sans-serif' };
  }
  return { fontFamily: 'System' };
}

export function AppText({
  variant = 'body',
  tone = 'primary',
  align,
  weight,
  style,
  children,
  ...props
}: AppTextProps) {
  const { colors } = useAppTheme();
  return (
    <Text
      {...props}
      style={[
        typography[variant],
        { color: toneColors(colors)[tone], textAlign: align },
        fontFamilyForWeight(weight),
        weight ? { fontWeight: weight } : null,
        style,
      ]}
    >
      {children}
    </Text>
  );
}
