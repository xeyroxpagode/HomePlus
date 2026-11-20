import React, { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, type StyleProp, type ViewStyle } from 'react-native';

import { useReducedMotion } from './homiVisual';

/**
 * Press feedback of the Homi surfaces.
 *
 * The reconciled motion family for a press is 80ms with a 0.97 scale and a
 * 0.85 opacity, and the B2 contract retires the spring family: no Homi
 * control uses a spring press. Under reduced motion the state change is
 * instant (the pressed color still changes, only the transform is dropped).
 */
export type HomiPressableProps = {
  children: React.ReactNode;
  onPress?: () => void;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  pressedStyle?: StyleProp<ViewStyle>;
  accessibilityRole?: 'button' | 'link' | 'none';
  accessibilityLabel?: string;
  accessibilityHint?: string;
  accessibilityState?: { disabled?: boolean; busy?: boolean; selected?: boolean };
};

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

const PRESS_DURATION = 80;
const PRESS_SCALE = 0.97;
const PRESS_OPACITY = 0.85;

export function HomiPressable({
  children,
  onPress,
  disabled,
  style,
  pressedStyle,
  accessibilityRole = 'button',
  accessibilityLabel,
  accessibilityHint,
  accessibilityState,
}: HomiPressableProps) {
  const reduceMotion = useReducedMotion();
  const scale = useRef(new Animated.Value(1)).current;
  const opacity = useRef(new Animated.Value(1)).current;

  useEffect(
    () => () => {
      scale.stopAnimation();
      opacity.stopAnimation();
    },
    [scale, opacity],
  );

  const animate = (toScale: number, toOpacity: number) => {
    if (reduceMotion) return;
    const timing = (value: Animated.Value, toValue: number) =>
      Animated.timing(value, {
        toValue,
        duration: PRESS_DURATION,
        easing: Easing.bezier(0.55, 0, 1, 0.45),
        useNativeDriver: true,
      });
    Animated.parallel([timing(scale, toScale), timing(opacity, toOpacity)]).start();
  };

  return (
    <AnimatedPressable
      onPress={onPress}
      disabled={disabled}
      onPressIn={() => animate(PRESS_SCALE, PRESS_OPACITY)}
      onPressOut={() => animate(1, 1)}
      accessibilityRole={accessibilityRole}
      accessibilityLabel={accessibilityLabel}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ ...accessibilityState, disabled }}
      style={[
        style,
        {
          opacity: disabled ? 0.45 : opacity,
          transform: [{ scale: disabled ? 1 : scale }],
        },
        pressedStyle,
      ]}
    >
      {children}
    </AnimatedPressable>
  );
}
