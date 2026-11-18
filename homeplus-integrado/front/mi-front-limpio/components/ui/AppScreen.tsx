import React from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  View,
  type ScrollViewProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView, type Edges } from 'react-native-safe-area-context';

import { layout, navigationGeometry, spacing } from '../../constants/theme';
import { useAppTheme } from '../../context/AppThemeContext';

export type AppScreenProps = {
  children: React.ReactNode;
  scroll?: boolean;
  padded?: boolean;
  keyboardAvoiding?: boolean;
  background?: 'base' | 'soft' | 'alt';
  bottomInset?: 'none' | 'tab' | 'fab' | 'sheet';
  centered?: boolean;
  constrained?: boolean;
  style?: StyleProp<ViewStyle>;
  contentContainerStyle?: StyleProp<ViewStyle>;
  scrollProps?: Omit<ScrollViewProps, 'contentContainerStyle'>;
  safeAreaEdges?: Edges;
};

const bottomInsets: Record<NonNullable<AppScreenProps['bottomInset']>, number> = {
  none: spacing[5],
  // SafeAreaView contributes the physical device inset; this padding reserves
  // the shared navigation geometry plus enough breathing room for the last row.
  tab: navigationGeometry.bottomBarHeight + navigationGeometry.bottomBarBreathingSpace + spacing[6],
  fab: navigationGeometry.fabHeight + navigationGeometry.bottomBarBreathingSpace + spacing[12],
  sheet: spacing[8],
};

export function AppScreen({
  children,
  scroll = false,
  padded = true,
  keyboardAvoiding = false,
  background = 'base',
  bottomInset = 'none',
  centered = false,
  constrained = padded,
  style,
  contentContainerStyle,
  scrollProps,
  safeAreaEdges,
}: AppScreenProps) {
  const { colors } = useAppTheme();
  const screenBackground = colors.background[background];
  const contentStyle: StyleProp<ViewStyle> = [
    {
      flexGrow: 1,
      width: '100%',
      maxWidth: constrained ? layout.screen.contentMaxWidth : undefined,
      alignSelf: 'center',
      paddingHorizontal: padded ? layout.screen.horizontalPadding : 0,
      paddingTop: layout.screen.topPadding,
      paddingBottom: bottomInsets[bottomInset],
    },
    centered ? { alignItems: 'center', justifyContent: 'center' } : null,
    contentContainerStyle,
  ];

  const body = scroll ? (
    <ScrollView
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
      {...scrollProps}
      contentContainerStyle={contentStyle}
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[{ flex: 1 }, contentStyle]}>{children}</View>
  );

  const wrappedBody = keyboardAvoiding ? (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ flex: 1 }}
    >
      {body}
    </KeyboardAvoidingView>
  ) : (
    body
  );

  return (
    <SafeAreaView edges={safeAreaEdges} style={[{ flex: 1, backgroundColor: screenBackground }, style]}>
      {wrappedBody}
    </SafeAreaView>
  );
}
