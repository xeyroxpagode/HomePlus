/**
 * Homi DEMO V1 — shared visual helpers.
 *
 * The Homi surfaces never invent colors, spacing or motion: every value is
 * read from the canonical HomePlus theme, so the conversation keeps the same
 * optical identity as the rest of the product (and follows the dark scheme
 * when the user selects it).
 *
 * Depth rule of the DEMO V1 closure, applied only to the Homi surfaces:
 *
 *   canvas            -> `colors.background.base` (no surface, no border)
 *   integrated content-> `colors.surface.card` + `border.subtle` + `shadows.card`
 *   interaction        -> `colors.surface.card` + `border.default` + `shadows.card`
 *   overlay            -> tone-tinted surface + the matching border color
 *
 * Shadows are never stacked: exactly one elevation level per surface.
 */

import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

import { useAppTheme } from '../../context/AppThemeContext';
import type { AppResolvedTheme } from '../../constants/theme';

/** True while the user asked the OS to reduce motion. */
export function useReducedMotion(): boolean {
  const [reduceMotion, setReduceMotion] = useState(false);

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

  return reduceMotion;
}

/** Canonical Planner task status labels (same wording as the Planner surfaces). */
export const homiTaskStatusLabels: Record<string, string> = {
  pending: 'Pendiente',
  completed: 'Completada',
  awaiting_verification: 'En verificación',
  correction_requested: 'Requiere corrección',
  verified: 'Verificada',
  cancelled: 'Cancelada',
};

export const homiTaskStatusTone = (
  status: string,
): 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info' => {
  switch (status) {
    case 'completed':
    case 'verified':
      return 'success';
    case 'awaiting_verification':
    case 'correction_requested':
      return 'warning';
    case 'cancelled':
      return 'danger';
    default:
      return 'neutral';
  }
};

export const homiTaskStatusLabel = (status: string): string =>
  homiTaskStatusLabels[status] ?? 'Pendiente';

/** `YYYY-MM-DD` (or an instant) rendered as the canonical short Planner date. */
export const homiFormatDate = (value?: string | null): string | null => {
  if (!value) return null;
  const date = value.includes('T') ? new Date(value) : new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('es-AR', { day: '2-digit', month: 'short' });
};

/** `HH:MM` of a date-only string, kept empty when there is no time. */
export const homiFormatTime = (value?: string | null): string | null => {
  if (!value) return null;
  if (/^\d{2}:\d{2}/.test(value)) return value.slice(0, 5);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
};

/** Message meta time: `14:05`. */
export const homiFormatClock = (value?: string | null): string | null => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
};

/**
 * Motion contract of the DEMO V1 Homi surfaces.
 *
 * Taken verbatim from the reconciled B2 interaction target so the React
 * Native implementation keeps the exact same clocks as the reference
 * prototype:
 *
 *   fast      140ms  a punctual state in place (chip, check, pressed)
 *   standard  220ms  one row or one disclosure
 *   structural 260ms a change of depth (open, close, appear)
 *
 *   exit rule: 0.75 x entrance, rounded to 10ms, never below 120ms
 *
 * No spring family is used anywhere, and reduced motion is opacity only.
 */
export const homiMotion = {
  fast: 140,
  standard: 220,
  structural: 260,
  exitFast: 120,
  exitStandard: 170,
  exitStructural: 195,
  /** The only transition allowed under reduced motion. */
  reducedFade: 120,
  /** Pending turn acknowledgement clock. */
  clockPending: 420,
  /** Thinking dots cadence. */
  clockThinking: 420,
} as const;

/** Easing of the reconciled B2 target, in React Native `Easing.bezier` form. */
export const homiEasing = {
  /** ENTER */
  in: [0.22, 1, 0.36, 1] as const,
  /** EXIT */
  out: [0.55, 0, 1, 0.45] as const,
  /** TRAVEL */
  move: [0.25, 0.46, 0.45, 0.94] as const,
};

/**
 * Semantic spacing of the DEMO V1 conversation.
 *
 * The reconciled target fixes eight semantic relationships; these are the
 * four the DEMO V1 conversation actually renders. `headerToContent` is the
 * one adaptation: the target value (6px) is not a canonical token of the
 * HomePlus theme, so the nearest canonical token (8px) is used instead of
 * introducing a new scale.
 */
export const homiSpacing = {
  /** inside one turn: icon ↔ text, bubble padding */
  intraTurn: 12,
  /** between turns */
  interTurn: 16,
  /** header → first content row */
  headerToContent: 8,
  /** timeline ↔ composer, fixed */
  composerGap: 24,
  /** between rows of the same block */
  rowGap: 8,
} as const;

export type HomiTheme = AppResolvedTheme;

/** Convenience hook: the resolved theme of the app. */
export const useHomiTheme = (): HomiTheme => useAppTheme();

/**
 * File size of an attachment, rendered with the canonical one-decimal form.
 */
export const homiFormatFileSize = (sizeBytes?: number | null): string | null => {
  if (!sizeBytes || sizeBytes <= 0) return null;
  return `${(sizeBytes / 1024).toFixed(1)} KB`;
};
