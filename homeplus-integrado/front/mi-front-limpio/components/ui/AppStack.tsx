import React from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';

import { layout } from '../../constants/theme';

export type AppStackGap = keyof typeof layout.stack;

type AppStackProps = {
  children: React.ReactNode;
  gap?: AppStackGap;
  direction?: 'vertical' | 'horizontal';
  align?: ViewStyle['alignItems'];
  justify?: ViewStyle['justifyContent'];
  wrap?: boolean;
  style?: StyleProp<ViewStyle>;
};

/** A shared rhythm primitive. Related content stays close; sections breathe. */
export function AppStack({
  children,
  gap = 'content',
  direction = 'vertical',
  align,
  justify,
  wrap = false,
  style,
}: AppStackProps) {
  return (
    <View
      style={[
        {
          flexDirection: direction === 'horizontal' ? 'row' : 'column',
          gap: layout.stack[gap],
          alignItems: align,
          justifyContent: justify,
          flexWrap: wrap ? 'wrap' : 'nowrap',
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}
