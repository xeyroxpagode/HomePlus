import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { HomePlusIcon } from '../../constants/icons';
import { spacing } from '../../constants/theme';
import { AppText } from '../ui/AppText';
import { Row } from '../ui/Row';
import { StatusBadge } from '../ui/StatusBadge';
import { AssetAvatar } from './AssetAvatar';
import { describeContextLine, lifecyclePill } from './assetLabels';
import type { AssetDto } from '../../services/assets';

export type AssetRowProps = {
  asset: AssetDto;
  onPress: () => void;
};

/**
 * Fila Root: avatar 40, nombre 15/600, contexto 12–13, chevron 16,
 * alto base 64 con crecimiento natural. Sin recorte tipográfico.
 */
export function AssetRow({ asset, onPress }: AssetRowProps) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const context = describeContextLine(asset);
  const pill = lifecyclePill(asset.lifecycle_status);

  return (
    <Row
      accessibilityRole="button"
      accessibilityLabel={context ? `${asset.name}. ${context}` : asset.name}
      onPress={onPress}
    >
      <AssetAvatar profile={asset.profile} size="root" />
      <View style={styles.content}>
        <View style={styles.titleLine}>
          <AppText variant="bodySmall" weight="600" style={styles.title}>
            {asset.name}
          </AppText>
          {pill ? <StatusBadge label={pill.label} tone={pill.tone} /> : null}
        </View>
        {context ? (
          <AppText variant="caption" tone="tertiary" numberOfLines={2}>
            {context}
          </AppText>
        ) : null}
      </View>
      <HomePlusIcon name="chevron-forward-outline" size={16} color={colors.text.tertiary} />
    </Row>
  );
}




function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  content: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  titleLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  title: {
    flexShrink: 1,
  },
});
}
