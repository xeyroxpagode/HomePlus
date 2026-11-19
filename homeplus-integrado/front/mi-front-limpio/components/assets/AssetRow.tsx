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
import { ASSET_PROFILE_LABEL, describeContextLine, lifecyclePill } from './assetLabels';
import type { AssetDto } from '../../services/assets';

export type AssetRowProps = {
  asset: AssetDto;
  onPress: () => void;
};

/**
 * Tarjeta de una columna: identidad visible y contexto breve, sin acciones anidadas.
 */
export function AssetRow({ asset, onPress }: AssetRowProps) {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const context = describeContextLine(asset);
  const pill = lifecyclePill(asset.lifecycle_status);
  const category = asset.category?.name ?? ASSET_PROFILE_LABEL[asset.profile];

  return (
    <Row
      accessibilityRole="button"
      accessibilityLabel={[asset.name, category, context !== category ? context : null, pill?.label].filter(Boolean).join('. ')}
      onPress={onPress}
      variant="card"
      divider={false}
      style={styles.card}
    >
      <AssetAvatar profile={asset.profile} size="detail" />
      <View style={styles.content}>
        <View style={styles.titleLine}>
          <AppText variant="body" weight="600" style={styles.title}>
            {asset.name}
          </AppText>
        </View>
        {category ? <AppText variant="bodySmall" tone="secondary">{category}</AppText> : null}
        {context && context !== category ? (
          <AppText variant="bodySmall" tone="secondary" numberOfLines={2}>
            {context}
          </AppText>
        ) : null}
        {pill ? <StatusBadge label={pill.label} tone={pill.tone} /> : null}
      </View>
      <HomePlusIcon name="chevron-forward-outline" size={20} color={colors.text.tertiary} />
    </Row>
  );
}




function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  card: { minHeight: 96, padding: spacing[4], backgroundColor: colors.surface.card },
  content: {
    flex: 1,
    minWidth: 0,
    gap: spacing[1],
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
