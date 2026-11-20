import React, { useMemo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '../ui/AppText';
import { HomePlusIcon } from '../../constants/icons';
import type { HomiTheme } from './homiVisual';
import { homiSpacing, useHomiTheme } from './homiVisual';

/**
 * Suggestion of the DEMO V1 welcome state.
 *
 * `planner_read` runs the real authorized READ tool of the Planner; `ask`
 * sends a conversation turn to HOMI-D. Nothing else is offered, because
 * nothing else is available in this closure.
 */
export type HomiSuggestion = {
  id: string;
  label: string;
  kind: 'planner_read' | 'ask';
  icon: 'calendar-outline' | 'chatbubble-ellipses-outline' | 'today-outline';
};

export const HOMI_DEMO_SUGGESTIONS: HomiSuggestion[] = [
  {
    id: 'planner-tasks',
    label: 'Ver mis tareas del Planner',
    kind: 'planner_read',
    icon: 'calendar-outline',
  },
  {
    id: 'ask-today',
    label: '¿Qué tengo pendiente hoy?',
    kind: 'ask',
    icon: 'chatbubble-ellipses-outline',
  },
  {
    id: 'ask-summary',
    label: 'Resumime la semana',
    kind: 'ask',
    icon: 'today-outline',
  },
];

type Props = {
  suggestions?: HomiSuggestion[];
  onSuggestion?: (suggestion: HomiSuggestion) => void;
};

/**
 * Welcome state of the DEMO V1 conversation.
 *
 * It states what Homi really does in this closure — converse and read the
 * Planner — and offers nothing else. No capability is advertised that the
 * runtime cannot honour.
 */
export function HomiEmptyState({ suggestions = HOMI_DEMO_SUGGESTIONS, onSuggestion }: Props) {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  return (
    <View style={styles.container}>
      <View style={styles.identity}>
        <View style={styles.badge}>
          <HomePlusIcon name="sparkles" size={22} color={theme.colors.terracotta[600]} />
        </View>
        <AppText variant="title2" weight="700">
          ¿En qué te puedo ayudar?
        </AppText>
        <AppText variant="bodySmall" tone="secondary" align="center">
          Puedo conversar con vos y leer las tareas de tu Planner.
        </AppText>
      </View>

      <View style={styles.suggestions}>
        {suggestions.map((suggestion) => (
          <Pressable
            key={suggestion.id}
            onPress={() => onSuggestion?.(suggestion)}
            accessibilityRole="button"
            accessibilityLabel={suggestion.label}
            style={({ pressed }) => [styles.suggestion, pressed && styles.suggestionPressed]}
          >
            <View style={styles.suggestionIcon}>
              <HomePlusIcon name={suggestion.icon} size={18} color={theme.colors.text.secondary} />
            </View>
            <AppText variant="bodySmall" weight="600" style={styles.suggestionLabel}>
              {suggestion.label}
            </AppText>
            <HomePlusIcon name="chevron-forward" size={16} color={theme.colors.text.muted} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const makeStyles = (theme: HomiTheme) =>
  StyleSheet.create({
    container: {
      gap: theme.spacing[5],
      paddingBottom: theme.spacing[2],
    },
    identity: {
      alignItems: 'center',
      gap: homiSpacing.intraTurn,
    },
    badge: {
      width: 56,
      height: 56,
      borderRadius: theme.radius.xxl,
      backgroundColor: theme.colors.terracotta[100],
      alignItems: 'center',
      justifyContent: 'center',
    },
    suggestions: {
      gap: homiSpacing.rowGap,
    },
    suggestion: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.intraTurn,
      minHeight: 56,
      paddingHorizontal: homiSpacing.intraTurn,
      paddingVertical: theme.spacing[2],
      borderRadius: theme.radius.md,
      backgroundColor: theme.colors.background.soft,
    },
    suggestionPressed: {
      opacity: 0.8,
    },
    suggestionIcon: {
      width: 32,
      height: 32,
      borderRadius: theme.radius.full,
      backgroundColor: theme.colors.surface.card,
      alignItems: 'center',
      justifyContent: 'center',
    },
    suggestionLabel: {
      flex: 1,
    },
  });
