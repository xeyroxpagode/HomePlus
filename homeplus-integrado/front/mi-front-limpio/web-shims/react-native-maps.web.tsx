/**
 * Web-only compatibility surface for react-native-maps.
 *
 * This file is resolved exclusively by metro.config.js when platform === 'web'.
 * It preserves the package's public names so existing production screens can
 * render on Expo Web. It is NOT used by iOS/Android builds.
 */
import React from 'react';
import { View } from 'react-native';

const NativeMapSurface = (props: any) => React.createElement(View, props, props.children);

export const MapView = NativeMapSurface;
export const Marker = NativeMapSurface;
export const Polyline = NativeMapSurface;
export const Polygon = NativeMapSurface;
export const Circle = NativeMapSurface;
export const Callout = NativeMapSurface;
export const UrlTile = NativeMapSurface;
export const TileOverlay = NativeMapSurface;
export const Overlay = NativeMapSurface;
export const Heatmap = NativeMapSurface;
export const Geojson = NativeMapSurface;
export const Camera = NativeMapSurface;
export const PROVIDER_GOOGLE = 'google';
export const PROVIDER_DEFAULT = 'default';

export default MapView;
