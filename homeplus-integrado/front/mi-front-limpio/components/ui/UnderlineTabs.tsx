import React from 'react';
import { StyleSheet, View } from 'react-native';

import { useAppTheme } from '../../context/AppThemeContext';
import { AppText } from './AppText';
import { InteractivePressable } from './InteractivePressable';

export type UnderlineTabOption<T extends string> = {
  value: T;
  label: string;
  accessibilityLabel?: string;
};

type UnderlineTabsProps<T extends string> = {
  value: T;
  options: readonly UnderlineTabOption<T>[];
  onChange: (value: T) => void;
  accessibilityLabel?: string;
  testID?: string;
};

/**
 * Navigation between peer destinations. Unlike SegmentedControl, this is not
 * a mode or filter switch: the selected destination keeps a stable edge and
 * terracotta baseline, matching the Finance information architecture.
 */
export function UnderlineTabs<T extends string>({
  value,
  options,
  onChange,
  accessibilityLabel,
  testID,
}: UnderlineTabsProps<T>) {
  const { colors, motion, spacing, visualErgonomics } = useAppTheme();

  return (
    <View
      accessibilityRole="tablist"
      accessibilityLabel={accessibilityLabel}
      testID={testID}
      style={[styles.root, { borderBottomColor: colors.border.subtle }]}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <InteractivePressable
            key={option.value}
            onPress={() => onChange(option.value)}
            haptic="light"
            pressScale={motion.scale.tab}
            pressedOpacity={0.88}
            accessibilityRole="tab"
            accessibilityLabel={option.accessibilityLabel ?? option.label}
            accessibilityState={{ selected }}
            style={[
              styles.tab,
              {
                minHeight: visualErgonomics.minimumInteractiveTarget,
                paddingHorizontal: spacing[2],
              },
              selected && { borderBottomWidth: 2, borderBottomColor: colors.brand },
            ]}
          >
            <AppText variant="bodySmall" weight={selected ? '800' : '600'} tone={selected ? 'primary' : 'secondary'} numberOfLines={1}>
              {option.label}
            </AppText>
          </InteractivePressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flexDirection: 'row',
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  tab: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: -StyleSheet.hairlineWidth,
  },
});
