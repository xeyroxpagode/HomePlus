import React from 'react';
import { Pressable, View, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { layout, spacing, touchTargets } from '../../constants/theme';
import { useAppTheme } from '../../context/AppThemeContext';
import { AppText } from './AppText';
import { AppAvatar } from './AppAvatar';
import { HomePlusIcon } from '../../constants/icons';
import { StatusBadge } from './StatusBadge';

export type AppTopBarProps = {
  personName: string;
  personAvatarUrl?: string | null;
  householdName: string;
  householdRole: string;
  onAvatarPress?: () => void;
  avatarTestID?: string;
  onHouseholdPress?: () => void;
  showChevron?: boolean;
  rightSlot?: React.ReactNode;
};

function getRoleDisplay(role: string): { label: string } {
  const roleLower = role.toLowerCase();
  const mapping: Record<string, { label: string }> = {
    coordinator: { label: 'Coordinador' },
    coordinador: { label: 'Coordinador' },
    adult: { label: 'Adulto' },
    adulto: { label: 'Adulto' },
    adolescent: { label: 'Adolescente' },
    adolescente: { label: 'Adolescente' },
    senior: { label: 'Adulto mayor' },
    adulto_mayor: { label: 'Adulto mayor' },
    child: { label: 'Niño' },
    guest: { label: 'Invitado' },
  };
  return mapping[roleLower] ?? { label: role };
}

export function AppTopBar({
  personName,
  personAvatarUrl,
  householdName,
  householdRole,
  onAvatarPress,
  avatarTestID,
  onHouseholdPress,
  showChevron = true,
  rightSlot,
}: AppTopBarProps) {
  const roleInfo = getRoleDisplay(householdRole);
  const insets = useSafeAreaInsets();
  const { colors } = useAppTheme();

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.background.base, borderBottomColor: colors.border.subtle }]}>
      <View style={styles.leftSection}>
        <AppAvatar
          imageUrl={personAvatarUrl}
          name={personName}
          size="md"
          showBorder
          onPress={onAvatarPress}
          testID={avatarTestID}
          accessibilityLabel={`Abrir perfil de ${personName}`}
        />
      </View>

      <Pressable
        onPress={onHouseholdPress}
        style={({ pressed }) => [
          styles.centerSection,
          { opacity: pressed ? 0.7 : 1 },
        ]}
        accessibilityRole="button"
        accessibilityLabel={`Cambiar hogar: ${householdName}`}
      >
        <View style={styles.householdInfo}>
          <View style={styles.householdRow}>
            <AppText variant="bodySmall" weight="700" style={styles.householdName}>
              {householdName}
            </AppText>
            {showChevron && (
              <HomePlusIcon name="chevron-down-outline" size={16} color={colors.text.tertiary} style={styles.chevron} />
            )}
          </View>
          <StatusBadge label={roleInfo.label} tone="neutral" style={styles.roleBadge} />
        </View>
      </Pressable>

      <View style={styles.rightSection}>
        {rightSlot ? (
          <View style={styles.rightSlot}>{rightSlot}</View>
        ) : (
          <View style={styles.rightPlaceholder} />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    minHeight: 60,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: layout.screen.horizontalPadding,
    paddingVertical: spacing[1],
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  leftSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  centerSection: {
    flex: 1,
    alignItems: 'center',
    paddingHorizontal: spacing[2],
  },
  householdInfo: {
    alignItems: 'center',
    gap: 0,
  },
  householdRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[1],
  },
  householdName: {},
  chevron: {
    opacity: 0.7,
  },
  roleBadge: {
    minHeight: 22,
    paddingHorizontal: spacing[2],
  },
  rightSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  rightSlot: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  rightPlaceholder: {
    width: touchTargets.normal,
  },
});
