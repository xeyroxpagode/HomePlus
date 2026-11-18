import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { AppText, AppAvatar, ActionPill, Row } from '../ui';
import { spacing } from '../../constants/theme';
import { FamilyMember } from '../../services/family';
import { HomePlusIcon } from '../../constants/icons';
import { RoleBadge } from './RoleBadge';

type MemberRowProps = {
  member: FamilyMember;
  isSelf: boolean;
  canManageMembers?: boolean;
  canChangeRoles?: boolean;
  onAction?: () => void;
  showActions?: boolean;
};

export const MemberRow: React.FC<MemberRowProps> = ({
  member,
  isSelf,
  canManageMembers = false,
  canChangeRoles = false,
  onAction,
  showActions = false,
}) => {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  return (
    <Row
      accessibilityLabel={`${member.display_name}${isSelf ? ", vos" : ""}`}
      onPress={onAction}
      disabled={!onAction}
    >
      <View style={styles.avatarContainer}>
        <AppAvatar
          name={member.display_name}
          imageUrl={member.avatar_url}
          size="sm"
        />
      </View>

      <View style={styles.infoContainer}>
        <View style={styles.nameRow}>
          <AppText variant="body" weight="600" numberOfLines={1} style={styles.nameText}>
            {member.display_name}
          </AppText>
          {isSelf ? (
            <ActionPill label="Vos" tone="success" disabled />
          ) : null}
        </View>

        <View style={styles.metaRow}>
          <RoleBadge role={member.role} />
        </View>
      </View>

      {showActions && (canManageMembers || canChangeRoles) ? (
        <View style={styles.actionContainer}>
          <HomePlusIcon name="person-circle-outline" size={21} color={colors.text.tertiary} />
        </View>
      ) : null}
    </Row>
  );
};



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  avatarContainer: {
    flexShrink: 0,
  },
  infoContainer: {
    flex: 1,
    gap: spacing[1],
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  nameText: {
    flexShrink: 1,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[1],
  },
  actionContainer: {
    flexShrink: 0,
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border.subtle,
    backgroundColor: colors.surface.soft,
  },
});
}
