import React from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';

import { useAppTheme } from '../../../context/AppThemeContext';
import { AppText } from '../../ui/AppText';
import { InteractivePressable } from '../../ui/InteractivePressable';

type FinanceOverviewCardsProps = {
  periodLabel: string;
  contextLabel: string;
  balance: string;
  expenses: string;
  income: string;
  onOpenAnalysis?: () => void;
};

export function FinanceOverviewCards({
  periodLabel,
  contextLabel,
  balance,
  expenses,
  income,
  onOpenAnalysis,
}: FinanceOverviewCardsProps) {
  const theme = useAppTheme();
  const styles = createStyles(theme);
  const { width, fontScale } = useWindowDimensions();
  const stackMetrics = width < 360 || fontScale >= 1.45;

  const hero = (
    <View
      style={styles.hero}
      accessible
      accessibilityLabel={`${periodLabel}, ${contextLabel}. Balance ${balance}. Ingresos ${income}. Gastos ${expenses}.`}
    >
      <AppText variant="bodySmall" weight="700" style={styles.heroEyebrow}>
        {periodLabel} · {contextLabel}
      </AppText>
      <AppText
        variant="hero"
        weight="900"
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.68}
        style={styles.heroBalance}
      >
        {balance}
      </AppText>
      <AppText variant="bodySmall" weight="600" style={styles.heroSupporting}>
        vs. {income} ingresado
      </AppText>
    </View>
  );

  return (
    <View style={styles.root} testID="finance-summary-overview">
      {onOpenAnalysis ? (
        <InteractivePressable
          onPress={onOpenAnalysis}
          accessibilityRole="button"
          accessibilityLabel={`Abrir análisis. Balance ${balance}`}
          pressedOpacity={0.92}
        >
          {hero}
        </InteractivePressable>
      ) : hero}

      <View style={[styles.metrics, stackMetrics && styles.metricsStacked]}>
        <FinanceMetricCard label="Gastos" value={expenses} tone="danger" />
        <FinanceMetricCard label="Ingresos" value={income} tone="success" />
      </View>
    </View>
  );
}

function FinanceMetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'danger' | 'success';
}) {
  const theme = useAppTheme();
  const styles = createStyles(theme);

  return (
    <View style={styles.metric} accessible accessibilityLabel={`${label}: ${value}`}>
      <AppText variant="bodySmall" tone="secondary" weight="600">
        {label}
      </AppText>
      <AppText
        variant="title2"
        tone={tone}
        weight="900"
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.72}
        style={styles.metricValue}
      >
        {value}
      </AppText>
    </View>
  );
}

function createStyles(theme: ReturnType<typeof useAppTheme>) {
  const { colors, radius, spacing } = theme;

  return StyleSheet.create({
    root: {
      gap: spacing[3],
    },
    hero: {
      minHeight: 168,
      borderRadius: radius.xl,
      backgroundColor: colors.terracotta[600],
      paddingHorizontal: spacing[4],
      paddingVertical: spacing[4],
      justifyContent: 'center',
      gap: spacing[2],
    },
    heroEyebrow: {
      color: colors.text.inverse,
      opacity: 0.9,
    },
    heroBalance: {
      color: colors.text.inverse,
      fontVariant: ['tabular-nums'],
    },
    heroSupporting: {
      color: colors.text.inverse,
      opacity: 0.82,
    },
    metrics: {
      flexDirection: 'row',
      gap: spacing[3],
    },
    metricsStacked: {
      flexDirection: 'column',
    },
    metric: {
      flex: 1,
      minHeight: 112,
      borderRadius: radius.lg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border.subtle,
      backgroundColor: colors.surface.card,
      paddingHorizontal: spacing[4],
      paddingVertical: spacing[4],
      justifyContent: 'center',
      gap: spacing[2],
    },
    metricValue: {
      fontVariant: ['tabular-nums'],
    },
  });
}
