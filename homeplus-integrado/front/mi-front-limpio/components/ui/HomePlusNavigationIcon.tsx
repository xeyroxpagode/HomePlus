import React from 'react';
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';

type HomePlusNavigationIconName = 'home' | 'family' | 'planner' | 'more';

type Props = {
  name: HomePlusNavigationIconName;
  size?: number;
  color: string;
};

/**
 * Navigation glyphs deliberately live apart from the broad Ionicons catalog.
 * They share a single rounded 2.25px stroke, matching the Figma shell at every
 * tab and avoiding the mixed optical weights from unrelated icon families.
 */
export function HomePlusNavigationIcon({ name, size = 25, color }: Props) {
  const common = {
    stroke: color,
    strokeWidth: 2.25,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    fill: 'none',
  };

  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {name === 'home' ? <>
        <Path {...common} d="M3.5 10.5 12 3.7l8.5 6.8" />
        <Path {...common} d="M5.7 9.3v10.2c0 .8.6 1.4 1.4 1.4h9.8c.8 0 1.4-.6 1.4-1.4V9.3" />
        <Path {...common} d="M9.5 20.8v-5.5h5v5.5" />
      </> : null}
      {name === 'family' ? <>
        <Circle {...common} cx="8.2" cy="8" r="2.7" />
        <Circle {...common} cx="16.2" cy="8.6" r="2.3" />
        <Path {...common} d="M3.7 19.6c.4-3 2.2-4.8 4.5-4.8s4.1 1.8 4.5 4.8" />
        <Path {...common} d="M13.3 15.4c2.2.1 3.7 1.6 4 4.2" />
      </> : null}
      {name === 'planner' ? <>
        <Rect {...common} x="3.6" y="4.8" width="16.8" height="15.4" rx="2.8" />
        <Line {...common} x1="3.8" y1="9.3" x2="20.2" y2="9.3" />
        <Line {...common} x1="8" y1="3.4" x2="8" y2="6.4" />
        <Line {...common} x1="16" y1="3.4" x2="16" y2="6.4" />
        <Circle fill={color} cx="8" cy="13.3" r="1" />
        <Circle fill={color} cx="12" cy="13.3" r="1" />
        <Circle fill={color} cx="16" cy="13.3" r="1" />
        <Circle fill={color} cx="8" cy="16.8" r="1" />
        <Circle fill={color} cx="12" cy="16.8" r="1" />
      </> : null}
      {name === 'more' ? <>
        <Circle fill={color} cx="5.5" cy="12" r="1.75" />
        <Circle fill={color} cx="12" cy="12" r="1.75" />
        <Circle fill={color} cx="18.5" cy="12" r="1.75" />
      </> : null}
    </Svg>
  );
}

