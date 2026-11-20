import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

import { AppText } from '../ui/AppText';
import { HomePlusIcon } from '../../constants/icons';
import type { HomiTheme } from './homiVisual';
import { homiEasing, homiMotion, useHomiTheme, useReducedMotion } from './homiVisual';

type Props = {
  /** Kept explicit: the row always describes the real thinking turn. */
  label?: string;
};

/**
 * THINK visual of the DEMO V1 conversation.
 *
 * It describes the only real state that exists between sending a turn and
 * receiving the answer: HOMI-D is resolving the turn. It never advertises a
 * tool, a plan or an execution, because none of those is a client state.
 */
export function HomiThinkingRow({ label = 'Homi está pensando' }: Props) {
  const theme = useHomiTheme();
  const reduceMotion = useReducedMotion();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  const dots = useRef([
    new Animated.Value(0),
    new Animated.Value(0),
    new Animated.Value(0),
  ]).current;

  useEffect(() => {
    if (reduceMotion) {
      dots.forEach((dot) => dot.setValue(1));
      return;
    }

    const animations = dots.map((dot, index) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(index * 140),
          Animated.timing(dot, {
            toValue: 1,
            duration: homiMotion.fast,
            easing: Easing.bezier(...homiEasing.in),
            useNativeDriver: true,
          }),
          Animated.timing(dot, {
            toValue: 0,
            duration: homiMotion.fast,
            easing: Easing.bezier(...homiEasing.out),
            useNativeDriver: true,
          }),
          Animated.delay(Math.max(0, homiMotion.clockThinking - index * 140)),
        ]),
      ),
    );

    animations.forEach((animation) => animation.start());
    return () => animations.forEach((animation) => animation.stop());
  }, [dots, reduceMotion]);

  return (
    <View style={styles.row} accessibilityRole="text" accessibilityLabel={label}>
      <View style={[styles.bubble, styles.assistantBubble]}>
        <View style={styles.header}>
          <View style={styles.identity}>
            <HomePlusIcon name="sparkles" size={14} color={theme.colors.terracotta[600]} />
            <AppText variant="micro" tone="brand" weight="700">
              HOMI
            </AppText>
          </View>
          <View style={styles.dots}>
            {dots.map((dot, index) => (
              <Animated.View
                key={index}
                style={[
                  styles.dot,
                  {
                    opacity: dot.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] }),
                    transform: [
                      {
                        scale: dot.interpolate({ inputRange: [0, 1], outputRange: [0.82, 1] }),
                      },
                    ],
                  },
                ]}
              />
            ))}
          </View>
        </View>
        <AppText variant="bodySmall" tone="secondary">
          {label}
        </AppText>
      </View>
    </View>
  );
}

const makeStyles = (theme: HomiTheme) =>
  StyleSheet.create({
    row: {
      flexDirection: 'row',
      justifyContent: 'flex-start',
    },
    bubble: {
      maxWidth: '82%',
      paddingHorizontal: theme.spacing[3],
      paddingVertical: theme.spacing[3],
      borderRadius: theme.radius.lg,
      borderTopLeftRadius: theme.radius.xs,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
      backgroundColor: theme.colors.surface.card,
      ...theme.shadows.card,
      gap: theme.spacing[2],
    },
    assistantBubble: {
      alignSelf: 'flex-start',
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing[2],
    },
    identity: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing[1],
    },
    dots: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
    },
    dot: {
      width: 6,
      height: 6,
      borderRadius: theme.radius.full,
      backgroundColor: theme.colors.terracotta[500],
    },
  });
