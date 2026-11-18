import React from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '../../components/ui';
import { layout } from '../../constants/theme';

type Props = { firstName: string; householdName?: string | null; rightSlot?: React.ReactNode };

function greeting(hour: number) {
  if (hour < 12) return 'Buen día';
  if (hour < 19) return 'Buenas tardes';
  return 'Buenas noches';
}

function formatHomeDate(value: Date) {
  const localized = value.toLocaleDateString('es-AR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  return localized.charAt(0).toLocaleUpperCase('es-AR') + localized.slice(1);
}

export function HomeWelcomeHeader({ firstName, rightSlot }: Props) {
  const now = new Date();
  return (
    <View style={styles.root}>
      <View style={styles.row}>
        <View style={styles.copy}>
          <AppText variant="title1" weight="600" numberOfLines={2} style={styles.greetingTitle}>{greeting(now.getHours())}, {firstName}</AppText>
          <AppText variant="bodySmall" tone="tertiary" style={styles.date}>
            {formatHomeDate(now)}
          </AppText>
        </View>
        {rightSlot ? <View>{rightSlot}</View> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { width: '100%', gap: layout.stack.component, marginBottom: layout.stack.content },
  row: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: layout.stack.component },
  copy: { flex: 1, gap: layout.stack.tight },
  greetingTitle: { fontSize: 26, lineHeight: 31, letterSpacing: -0.3 },
  date: {},
});
