import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { HomePlusIcon, type HomePlusIconName } from '../../constants/icons';
import { motion, radius, spacing, touchTargets } from '../../constants/theme';
import { useAppTheme } from '../../context/AppThemeContext';
import { AppText } from './AppText';
import { HomePlusNavigationIcon } from './HomePlusNavigationIcon';
import { InteractivePressable } from './InteractivePressable';

export type FloatingNavigationVariant = 'main' | 'section';
export type FloatingNavigationAppearance = 'auto' | 'light' | 'dark';
export type FloatingNavigationDisplay = 'icon-only' | 'icon-label' | 'label-only';
export type FloatingNavigationSize = 'compact' | 'regular';

export const floatingNavigationMetrics = {
  mainRegularHeight: 62,
  mainCompactHeight: 58,
  sectionRegularHeight: 56,
  sectionCompactHeight: 48,
} as const;

export type FloatingNavigationItem = {
  id: string;
  icon: HomePlusIconName;
  label?: string;
  badge?: number;
  isAction?: boolean;
  accessibilityLabel?: string;
  testID?: string;
  /** Optical correction only; the semantic icon remains unchanged. */
  iconSize?: number;
  iconOffsetY?: number;
};

type NavigationPalette = {
  surface: string;
  border: string;
  icon: string;
  label: string;
  active: string;
  activeIcon: string;
  actionIcon: string;
  actionPressed: string;
  badge: string;
  badgeText: string;
};

export type NavigationItemProps = {
  item: FloatingNavigationItem;
  active: boolean;
  variant: FloatingNavigationVariant;
  display: FloatingNavigationDisplay;
  palette: NavigationPalette;
  accentColor: string;
  reduceMotion: boolean;
  onPress: () => void;
};

/** A single action shared by the main and contextual floating navigation bars. */
export function NavigationItem({
  item,
  active,
  variant,
  display,
  palette,
  accentColor,
  reduceMotion,
  onPress,
}: NavigationItemProps) {
  const styles = useThemeStyles(createStylesForTheme);

  const [pressed, setPressed] = useState(false);
  const previousActive = useRef(active);
  const focusProgress = useRef(new Animated.Value(active ? 1 : 0)).current;
  const showIcon = display !== 'label-only';
  const showLabel = display !== 'icon-only' && Boolean(item.label);
  const iconSize = item.iconSize ?? (item.isAction ? 25 : variant === 'main' ? 22 : 20);
  const mainNavigationIcon = variant === 'main' && !item.isAction
    ? ({ HomeTab: 'home', FamilyTab: 'family', PlannerTab: 'planner', MoreTab: 'more' } as const)[item.id]
    : undefined;

  useEffect(() => {
    if (previousActive.current === active) return;
    previousActive.current = active;
    focusProgress.stopAnimation();

    if (reduceMotion) {
      focusProgress.setValue(active ? 1 : 0);
      return;
    }

    Animated.timing(focusProgress, {
      toValue: active ? 1 : 0,
      duration: motion.navActive,
      easing: Easing.bezier(0.22, 1, 0.36, 1),
      useNativeDriver: true,
    }).start();
  }, [active, focusProgress, reduceMotion]);

  const iconOpacity = focusProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [0.82, 1],
  });

  return (
    <InteractivePressable
      accessibilityRole={item.isAction ? 'button' : 'tab'}
      accessibilityLabel={item.accessibilityLabel ?? item.label ?? item.id}
      testID={item.testID}
      accessibilityState={{ selected: active }}
      onPress={onPress}
      onPressIn={() => setPressed(true)}
      onPressOut={() => setPressed(false)}
      haptic="none"
      pressScale={1}
      pressedOpacity={item.isAction ? 0.98 : 0.94}
      style={[
        styles.item,
        variant === 'section' ? styles.sectionItem : null,
        item.isAction ? styles.actionItem : null,
      ]}
    >
      {showIcon ? (
        <View
          style={[
            styles.iconSlot,
            item.isAction
              ? [
                styles.actionSlot,
                {
                  backgroundColor: pressed ? palette.actionPressed : accentColor,
                  borderColor: palette.surface,
                },
              ]
              : null,
          ]}
        >
          {item.isAction ? (
            <Animated.View
              style={{ transform: [{ translateY: item.iconOffsetY ?? 0 }] }}
            >
              <HomePlusIcon name={item.icon} size={iconSize} color={palette.actionIcon} />
            </Animated.View>
          ) : (
            <Animated.View
              style={{
                opacity: iconOpacity,
                transform: [{ translateY: item.iconOffsetY ?? 0 }],
              }}
            >
              {mainNavigationIcon ? (
                <HomePlusNavigationIcon
                  name={mainNavigationIcon}
                  size={variant === 'main' ? 25 : iconSize}
                  color={active ? palette.activeIcon : palette.icon}
                />
              ) : (
                <HomePlusIcon
                  name={item.icon}
                  size={iconSize}
                  color={active ? palette.activeIcon : palette.icon}
                />
              )}
            </Animated.View>
          )}
          {item.badge && item.badge > 0 ? (
            <View style={[styles.badge, { backgroundColor: palette.badge }]}>
              <AppText variant="micro" style={[styles.badgeText, { color: palette.badgeText }]}>
                {item.badge > 99 ? '99+' : String(item.badge)}
              </AppText>
            </View>
          ) : null}
        </View>
      ) : null}
      {showLabel ? (
        <AppText
          variant="caption"
          weight={active ? '700' : '600'}
          style={[styles.label, { color: active ? (display === 'label-only' ? palette.activeIcon : palette.active) : palette.label }]}
          numberOfLines={1}
        >
          {item.label}
        </AppText>
      ) : null}
    </InteractivePressable>
  );
}

export type FloatingNavigationBarProps = {
  items: FloatingNavigationItem[];
  activeId?: string;
  onSelect: (item: FloatingNavigationItem) => void;
  variant?: FloatingNavigationVariant;
  display?: FloatingNavigationDisplay;
  appearance?: FloatingNavigationAppearance;
  size?: FloatingNavigationSize;
  style?: StyleProp<ViewStyle>;
  accentColor?: string;
  activeSurfaceColor?: string;
};

/**
 * Official HomePlus floating navigation system. It supports the app-level
 * navigation bar as well as compact, contextual controls over rich content.
 */
export function FloatingNavigationBar({
  items,
  activeId,
  onSelect,
  variant = 'main',
  display = 'icon-only',
  appearance = 'auto',
  size = 'regular',
  style,
  accentColor,
  activeSurfaceColor,
}: FloatingNavigationBarProps) {
  const { shadows } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const theme = useAppTheme();
  const { colors: themeColors, resolvedScheme } = theme;
  const resolvedAccentColor = accentColor ?? themeColors.brand;
  const [width, setWidth] = useState(0);
  const [reduceMotion, setReduceMotion] = useState(false);
  const matchedActiveIndex = items.findIndex((item) => item.id === activeId && !item.isAction);
  const hasActiveItem = matchedActiveIndex >= 0;
  const activeIndex = Math.max(0, matchedActiveIndex);
  const activePosition = useRef(new Animated.Value(activeIndex)).current;
  const hasPositionedActiveIndicator = useRef(false);
  const resolvedAppearance = appearance === 'auto'
    ? resolvedScheme
    : appearance;
  const palette = useMemo<NavigationPalette>(() => {
    if (resolvedAppearance === 'dark') {
      return {
        surface: themeColors.surface.elevated,
        border: themeColors.border.default,
        icon: themeColors.text.tertiary,
        label: themeColors.text.secondary,
        active: resolvedAccentColor,
        activeIcon: resolvedAccentColor,
        actionIcon: themeColors.text.inverse,
        actionPressed: themeColors.brandPressed,
        badge: themeColors.danger.base,
        badgeText: themeColors.text.primary,
      };
    }

    return {
      surface: themeColors.surface.card,
      border: themeColors.border.default,
      icon: themeColors.text.tertiary,
      label: themeColors.text.secondary,
      active: resolvedAccentColor,
      activeIcon: resolvedAccentColor,
      actionIcon: themeColors.text.inverse,
      actionPressed: themeColors.brandPressed,
      badge: themeColors.danger.base,
      badgeText: themeColors.text.inverse,
    };
  }, [resolvedAccentColor, resolvedAppearance, themeColors]);
  const resolvedActiveSurfaceColor = activeSurfaceColor
    ?? themeColors.brandSoft;
  const itemWidth = width > 0
    ? Math.max(0, width - spacing[2]) / Math.max(items.length, 1)
    : 0;
  const barHeight = variant === 'main'
    ? (size === 'compact' ? floatingNavigationMetrics.mainCompactHeight : floatingNavigationMetrics.mainRegularHeight)
    : (size === 'compact' ? floatingNavigationMetrics.sectionCompactHeight : floatingNavigationMetrics.sectionRegularHeight);
  const isSectionPill = variant === 'section' && display === 'label-only';
  const activeSize = variant === 'main'
    ? (size === 'compact' ? 44 : 46)
    : (size === 'compact' ? 36 : 42);
  const activeWidth = isSectionPill ? Math.max(0, itemWidth - spacing[1]) : activeSize;
  const activeHeight = isSectionPill ? (size === 'compact' ? 40 : 46) : activeSize;
  const activeOffset = itemWidth > 0
    ? spacing[1] + (itemWidth - activeWidth) / 2
    : 0;

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
    if (!hasActiveItem) return undefined;

    activePosition.stopAnimation();
    if (!hasPositionedActiveIndicator.current || reduceMotion) {
      hasPositionedActiveIndicator.current = true;
      activePosition.setValue(activeIndex);
      return undefined;
    }

    const animation = Animated.timing(activePosition, {
      toValue: activeIndex,
      duration: motion.navActive,
      easing: Easing.bezier(0.22, 1, 0.36, 1),
      useNativeDriver: true,
    });
    animation.start();

    return () => animation.stop();
  }, [activeIndex, activePosition, hasActiveItem, reduceMotion]);

  const translateX = itemWidth > 0
    ? Animated.add(Animated.multiply(activePosition, itemWidth), activeOffset)
    : 0;

  return (
    <View
      accessibilityRole="tablist"
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      style={[
        styles.barFrame,
        { height: barHeight, backgroundColor: palette.surface, borderColor: palette.border, ...theme.shadows.shadow2 },
        variant === 'section' ? styles.sectionBar : null,
        style,
      ]}
    >
      <View style={styles.barClip}>
        {hasActiveItem && itemWidth > 0 ? (
          <Animated.View
            pointerEvents="none"
            style={[
              styles.activeSurface,
              {
                width: activeWidth,
                height: activeHeight,
                borderRadius: radius.full,
                backgroundColor: resolvedActiveSurfaceColor,
                borderColor: themeColors.border.subtle,
                top: (barHeight - activeHeight) / 2,
                transform: [{ translateX }],
              },
            ]}
          />
        ) : null}
        <View style={styles.itemsRow}>
          {items.map((item) => (
            <NavigationItem
              key={item.id}
              item={item}
              active={item.id === activeId && !item.isAction}
              variant={variant}
              display={display}
              palette={palette}
              accentColor={resolvedAccentColor}
              reduceMotion={reduceMotion}
              onPress={() => onSelect(item)}
            />
          ))}
        </View>
      </View>
    </View>
  );
}



function createStylesForTheme({ shadows }: Pick<AppResolvedTheme, 'shadows'>) {
  return StyleSheet.create({
  barFrame: {
    width: '100%',
    borderRadius: radius.full,
    borderWidth: StyleSheet.hairlineWidth,
    ...shadows.shadow2,
  },
  barClip: {
    flex: 1,
    borderRadius: radius.full,
    paddingHorizontal: spacing[1],
    justifyContent: 'center',
    overflow: 'hidden',
  },
  sectionBar: {
    paddingHorizontal: spacing[1],
    ...shadows.shadow2,
  },
  itemsRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  item: {
    flex: 1,
    minWidth: 0,
    minHeight: touchTargets.normal,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    zIndex: 1,
  },
  sectionItem: {
    minHeight: touchTargets.normal,
  },
  iconSlot: {
    width: touchTargets.normal,
    height: touchTargets.normal,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionItem: {
    minHeight: touchTargets.normal,
  },
  actionSlot: {
    width: 50,
    height: 50,
    borderRadius: radius.full,
    borderWidth: 2,
    ...shadows.shadow2,
  },
  activeSurface: {
    position: 'absolute',
    left: 0,
    borderWidth: StyleSheet.hairlineWidth,
  },
  badge: {
    position: 'absolute',
    top: 2,
    right: 1,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
    borderWidth: 1.5,
    borderColor: '#FFFFFF',
  },
  badgeText: {
    fontSize: 9,
    lineHeight: 11,
  },
  label: {
    maxWidth: '100%',
    textAlign: 'center',
  },
});
}
