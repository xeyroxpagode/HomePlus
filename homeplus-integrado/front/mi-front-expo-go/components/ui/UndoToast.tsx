import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Keyboard, Platform, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { HomePlusIcon } from '../../constants/icons';
import { useAppTheme } from '../../context/AppThemeContext';
import { AppText } from './AppText';
import { InteractivePressable } from './InteractivePressable';

type UndoToastProps = {
  visible: boolean;
  message: string;
  tone?: 'success' | 'error';
  onUndo?: () => void;
  onDismiss: () => void;
  duration?: number;
  bottomOffset?: number;
  avoidKeyboard?: boolean;
};

export function UndoToast({
  visible,
  message,
  tone = 'success',
  onUndo,
  onDismiss,
  duration = 5000,
  bottomOffset,
  avoidKeyboard = true,
}: UndoToastProps) {
  const { colors, motion, navigationGeometry, radius, shadows, spacing, touchTargets } = useAppTheme();
  const insets = useSafeAreaInsets();
  const [rendered, setRendered] = useState(visible);
  const [reduceMotion, setReduceMotion] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const opacity = useRef(new Animated.Value(visible ? 1 : 0)).current;
  const translateY = useRef(new Animated.Value(visible ? 0 : spacing[3])).current;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const completedRef = useRef(false);
  const onDismissRef = useRef(onDismiss);
  const onUndoRef = useRef(onUndo);

  onDismissRef.current = onDismiss;
  onUndoRef.current = onUndo;

  useEffect(() => {
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (mounted) setReduceMotion(enabled);
    });
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (!avoidKeyboard || Platform.OS !== 'ios') return undefined;
    const show = Keyboard.addListener('keyboardWillShow', (event) => setKeyboardHeight(event.endCoordinates.height));
    const hide = Keyboard.addListener('keyboardWillHide', () => setKeyboardHeight(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, [avoidKeyboard]);

  useEffect(() => {
    const clearTimer = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };
    const finish = (notify: boolean) => {
      if (completedRef.current) return;
      completedRef.current = true;
      clearTimer();
      const durationMs = reduceMotion ? 0 : motion.fade;
      Animated.parallel([
        Animated.timing(opacity, { toValue: 0, duration: durationMs, useNativeDriver: true }),
        Animated.timing(translateY, { toValue: reduceMotion ? 0 : spacing[3], duration: durationMs, useNativeDriver: true }),
      ]).start(({ finished }) => {
        if (!finished && durationMs > 0) return;
        setRendered(false);
        if (notify) onDismissRef.current();
      });
    };

    opacity.stopAnimation();
    translateY.stopAnimation();
    clearTimer();

    if (visible) {
      completedRef.current = false;
      setRendered(true);
      opacity.setValue(reduceMotion ? 1 : 0);
      translateY.setValue(reduceMotion ? 0 : spacing[3]);
      Animated.parallel([
        Animated.timing(opacity, { toValue: 1, duration: reduceMotion ? 0 : motion.fade, useNativeDriver: true }),
        Animated.timing(translateY, { toValue: 0, duration: reduceMotion ? 0 : motion.normal, useNativeDriver: true }),
      ]).start();
      timerRef.current = setTimeout(() => finish(true), duration);
    } else if (rendered) {
      finish(false);
    }

    return () => {
      clearTimer();
      opacity.stopAnimation();
      translateY.stopAnimation();
    };
  }, [duration, motion.fade, motion.normal, opacity, reduceMotion, rendered, spacing, translateY, visible]);

  if (!rendered) return null;

  const shellBottom = insets.bottom
    + navigationGeometry.bottomBarHeight
    + navigationGeometry.bottomBarBreathingSpace
    + spacing[2];
  const resolvedBottom = bottomOffset ?? Math.max(shellBottom, keyboardHeight + spacing[2]);
  const iconColor = tone === 'success' ? colors.success.strong : colors.danger.strong;

  const handleUndo = () => {
    if (completedRef.current) return;
    completedRef.current = true;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    onUndoRef.current?.();
    Animated.parallel([
      Animated.timing(opacity, { toValue: 0, duration: reduceMotion ? 0 : motion.fade, useNativeDriver: true }),
      Animated.timing(translateY, { toValue: reduceMotion ? 0 : spacing[3], duration: reduceMotion ? 0 : motion.fade, useNativeDriver: true }),
    ]).start(() => {
      setRendered(false);
      onDismissRef.current();
    });
  };

  return (
    <Animated.View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[
        styles.toastContainer,
        { bottom: resolvedBottom, left: spacing[4], right: spacing[4], opacity, transform: [{ translateY }] },
      ]}
    >
      <View
        style={[
          styles.toastContent,
          shadows.elevated,
          {
            backgroundColor: colors.surface.card,
            borderColor: colors.border.subtle,
            borderRadius: radius.md,
            paddingHorizontal: spacing[4],
            paddingVertical: spacing[2],
          },
        ]}
      >
        {onUndo ? null : (
          <View style={{ marginRight: spacing[2] }}>
            <HomePlusIcon name={tone === 'success' ? 'checkmark-circle' : 'alert-circle'} size={20} color={iconColor} />
          </View>
        )}
        <AppText variant="bodySmall" weight="700" style={[styles.toastMessage, { color: colors.text.primary }]}>
          {message}
        </AppText>
        {onUndo ? (
          <InteractivePressable
            accessibilityRole="button"
            accessibilityLabel="Deshacer"
            onPress={handleUndo}
            haptic="none"
            pressScale={motion.scale.button}
            style={[
              styles.undoButton,
              {
                minHeight: touchTargets.normal,
                minWidth: touchTargets.normal,
                borderRadius: radius.xs,
                backgroundColor: colors.brand,
                paddingHorizontal: spacing[3],
                marginLeft: spacing[2],
              },
            ]}
          >
            <AppText variant="micro" weight="800" style={{ color: colors.text.inverse }}>
              Deshacer
            </AppText>
          </InteractivePressable>
        ) : null}
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  toastContainer: {
    position: 'absolute',
    zIndex: 1000,
  },
  toastContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
  },
  toastMessage: {
    flex: 1,
  },
  undoButton: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});

