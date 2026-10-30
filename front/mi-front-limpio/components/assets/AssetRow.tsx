import React from 'react';
import { StyleSheet, View } from 'react-native';

import { HomePlusIcon } from '../../constants/icons';
import { colors, motion, spacing } from '../../constants/theme';
import { AppText } from '../ui/AppText';
import { InteractivePressable } from '../ui/InteractivePressable';
import { StatusBadge } from '../ui/StatusBadge';
import { AssetAvatar } from './AssetAvatar';
import { describeContextLine, lifecyclePill } from './assetLabels';
import type { AssetDto } from '../../services/assets';

export type AssetRowProps = {
  asset: AssetDto;
  onPress: (assetId: string) => void;
};

/**
 * Fila Root: avatar 40, nombre 14/600 (hasta 2 líneas), contexto 12 en la
 * línea de metadatos, estado de ciclo de vida como badge en esa misma línea y
 * chevron 16. El nombre nunca compite con el estado: toma todo el ancho
 * disponible y el badge se achica sólo si hace falta.
 */
export function AssetRowImpl({ asset, onPress }: AssetRowProps) {
  const context = describeContextLine(asset);
  const pill = lifecyclePill(asset.lifecycle_status);
  const spoken = [asset.name, context, pill?.label].filter(Boolean).join('. ');

  return (
    <InteractivePressable
      accessibilityRole="button"
      accessibilityLabel={spoken}
      onPress={() => onPress(asset.id)}
      haptic="light"
      pressScale={motion.scale.card}
      pressedOpacity={0.85}
      style={styles.row}
    >
      <AssetAvatar profile={asset.profile} size="root" />
      <View style={styles.content}>
        <AppText variant="bodySmall" weight="600" numberOfLines={2} style={styles.title}>
          {asset.name}
        </AppText>
        {context || pill ? (
          <View style={styles.metaLine}>
            {pill ? <StatusBadge label={pill.label} tone={pill.tone} /> : null}
            {context ? (
              <AppText variant="caption" tone="tertiary" numberOfLines={2} style={styles.context}>
                {context}
              </AppText>
            ) : null}
          </View>
        ) : null}
      </View>
      <View accessible={false} importantForAccessibility="no">
        <HomePlusIcon name="chevron-forward-outline" size={16} color={colors.text.tertiary} />
      </View>
    </InteractivePressable>
  );
}

export const AssetRow = React.memo(AssetRowImpl);

const styles = StyleSheet.create({
  row: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
    paddingVertical: spacing[2],
    borderBottomWidth: 1,
    borderBottomColor: colors.border.subtle,
  },
  content: {
    flex: 1,
    minWidth: 0,
    gap: spacing[1],
  },
  title: {
    flexShrink: 1,
  },
  metaLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
    minWidth: 0,
  },
  context: {
    flexShrink: 1,
  },
});
