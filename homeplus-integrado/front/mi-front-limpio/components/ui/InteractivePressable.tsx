import React, { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Pressable,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { useReducedMotion } from '../../hooks/useReducedMotion';
import { motion } from '../../constants/theme';
import { lightHaptic, mediumHaptic } from '../../utils/haptics';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export type InteractionHaptic = 'none' | 'light' | 'medium';

export type InteractivePressableProps = Omit<PressableProps, 'children' | 'style'> & {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  pressScale?: number;
  pressedOpacity?: number;
  haptic?: InteractionHaptic;
};

export function InteractivePressable({
  children,
  disabled,
  style,
  pressScale = motion.scale.button,
  pressedOpacity = 0.9,
  haptic = 'none',
  onPressIn,
  onPressOut,
  ...pressableProps
}: InteractivePressableProps) {
  const scale = useRef(new Animated.Value(1)).current;
  const [pressed, setPressed] = useState(false);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (disabled || reduceMotion) {
      scale.stopAnimation();
      scale.setValue(1);
      setPressed(false);
    }
  }, [disabled, reduceMotion, scale]);

  const handlePressIn: NonNullable<PressableProps['onPressIn']> = (event) => {
    if (!disabled) {
      setPressed(true);
      if (haptic === 'light') void lightHaptic();
      if (haptic === 'medium') void mediumHaptic();
      if (!reduceMotion && pressScale !== 1) {
        Animated.spring(scale, {
          toValue: pressScale,
          ...motion.spring.press,
          useNativeDriver: true,
        }).start();
      }
    }
    onPressIn?.(event);
  };

  const handlePressOut: NonNullable<PressableProps['onPressOut']> = (event) => {
    setPressed(false);
    if (!reduceMotion && pressScale !== 1) {
      Animated.spring(scale, {
        toValue: 1,
        ...motion.spring.release,
        useNativeDriver: true,
      }).start();
    }
    onPressOut?.(event);
  };

  return (
    <AnimatedPressable
      {...pressableProps}
      disabled={disabled}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      style={[
        style,
        {
          opacity: disabled ? 0.58 : pressed ? pressedOpacity : 1,
          transform: pressScale === 1 || reduceMotion ? undefined : [{ scale }],
        },
      ]}
    >
      {children}
    </AnimatedPressable>
  );
}
