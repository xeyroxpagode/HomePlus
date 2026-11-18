import React, { useEffect, useRef } from 'react';
import {
  Animated,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { KeyboardAwareScrollView } from 'react-native-keyboard-aware-scroll-view';
import { colors, layout, radius, shadows, spacing } from '../constants/theme';

type AuthScreenLayoutProps = {
  children: React.ReactNode;
  screenIndicator?: string;
  centerContent?: boolean;
  dismissKeyboardOnTapOutside?: boolean;
  presentation?: 'standard' | 'premium';
};

export const AuthScreenLayout = ({
  children,
  centerContent = false,
  dismissKeyboardOnTapOutside = true,
  presentation = 'standard',
}: AuthScreenLayoutProps) => {
  const isPremium = presentation === 'premium';
  const contentOpacity = useRef(new Animated.Value(isPremium ? 0 : 1)).current;
  const contentTranslateY = useRef(new Animated.Value(isPremium ? 10 : 0)).current;

  useEffect(() => {
    if (!isPremium) {
      contentOpacity.setValue(1);
      contentTranslateY.setValue(0);
      return;
    }

    contentOpacity.setValue(0);
    contentTranslateY.setValue(10);

    Animated.parallel([
      Animated.timing(contentOpacity, {
        toValue: 1,
        duration: 240,
        useNativeDriver: true,
      }),
      Animated.timing(contentTranslateY, {
        toValue: 0,
        duration: 240,
        useNativeDriver: true,
      }),
    ]).start();
  }, [contentOpacity, contentTranslateY, isPremium]);

  const handlePressOutside = () => {
    if (dismissKeyboardOnTapOutside) {
      Keyboard.dismiss();
    }
  };

  const scrollContent = (
    <KeyboardAwareScrollView
      style={styles.flex}
      contentContainerStyle={[
        styles.scrollContent,
        isPremium ? styles.premiumScrollContent : null,
        centerContent ? styles.centerContent : styles.startContent,
      ]}
      keyboardShouldPersistTaps="handled"
      enableOnAndroid={true}
      extraScrollHeight={24}
      showsVerticalScrollIndicator={false}
    >
      <Animated.View
        style={[
          styles.inner,
          isPremium ? styles.premiumInner : null,
          {
            opacity: contentOpacity,
            transform: [{ translateY: contentTranslateY }],
          },
        ]}
      >
        {children}
      </Animated.View>
    </KeyboardAwareScrollView>
  );

  return (
    <SafeAreaView style={[styles.container, isPremium ? styles.premiumContainer : null]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 12 : 0}
      >
        {dismissKeyboardOnTapOutside ? (
          <Pressable style={styles.flex} onPress={handlePressOutside}>
            {scrollContent}
          </Pressable>
        ) : (
          scrollContent
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background.base },
  premiumContainer: { backgroundColor: colors.background.base },
  flex: { flex: 1 },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: layout.screen.horizontalPaddingWide,
    paddingTop: layout.screen.bottomPadding,
    paddingBottom: layout.screen.bottomPadding,
  },
  premiumScrollContent: {
    paddingHorizontal: layout.screen.horizontalPadding,
    paddingTop: spacing[7],
    paddingBottom: spacing[7],
  },
  centerContent: { justifyContent: 'center' },
  startContent: { justifyContent: 'flex-start' },
  inner: { width: '100%' },
  premiumInner: {
    width: '100%',
    maxWidth: 480,
    alignSelf: 'center',
    backgroundColor: colors.surface.card,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    borderRadius: radius.xl,
    paddingHorizontal: spacing[6],
    paddingVertical: spacing[7],
    ...shadows.shadow2,
  },
});
