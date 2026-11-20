import React, { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '../ui/AppText';
import { StatusBadge, type StatusBadgeTone } from '../ui/StatusBadge';
import { HomePlusIcon } from '../../constants/icons';
import type { HomiTaskDto } from '../../services/homi/homiMessages';
import type { HomiTheme } from './homiVisual';
import {
  homiFormatDate,
  homiFormatTime,
  homiSpacing,
  homiTaskStatusLabel,
  homiTaskStatusTone,
  useHomiTheme,
} from './homiVisual';

type Props = {
  task: HomiTaskDto;
};

/**
 * TaskCard of the DEMO V1 Planner READ journey.
 *
 * It follows the canonical HomePlus task row pattern: one title, the real
 * responsible, the real date and the real status. Nothing is inferred on the
 * client — every field comes from the task DTO returned by the authorized
 * Homi READ tool, and an absent field is simply not rendered.
 */
export function HomiTaskCard({ task }: Props) {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  const date = homiFormatDate(task.due_date);
  const time = homiFormatTime(task.due_time);
  const label = homiTaskStatusLabel(task.status);
  const tone = homiTaskStatusTone(task.status) as StatusBadgeTone;

  const meta: string[] = [];
  if (date) meta.push(time ? `${date} · ${time}` : date);
  if (task.requires_verification === true) meta.push('Requiere verificación');

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.icon}>
          <HomePlusIcon name="checkbox-outline" size={16} color={theme.colors.terracotta[600]} />
        </View>
        <AppText variant="bodySmall" weight="700" numberOfLines={2} style={styles.title}>
          {task.title}
        </AppText>
      </View>

      {meta.length > 0 ? (
        <View style={styles.metaRow}>
          <HomePlusIcon name="calendar-outline" size={14} color={theme.colors.text.tertiary} />
          <AppText variant="caption" tone="tertiary">
            {meta.join(' · ')}
          </AppText>
        </View>
      ) : null}

      <View style={styles.footer}>
        <StatusBadge label={label} tone={tone} icon="ellipse-outline" />
      </View>
    </View>
  );
}

const makeStyles = (theme: HomiTheme) =>
  StyleSheet.create({
    card: {
      padding: homiSpacing.intraTurn,
      borderRadius: theme.radius.md,
      backgroundColor: theme.colors.surface.soft,
      gap: homiSpacing.rowGap,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing[2],
    },
    icon: {
      width: 28,
      height: 28,
      borderRadius: theme.radius.sm,
      backgroundColor: theme.colors.surface.card,
      alignItems: 'center',
      justifyContent: 'center',
    },
    title: {
      flex: 1,
    },
    metaRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
    },
    footer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing[2],
    },
  });
