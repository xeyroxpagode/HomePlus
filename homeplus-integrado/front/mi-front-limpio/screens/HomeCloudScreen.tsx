
import { useThemeStyles } from '../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../constants/theme';
import { productNames } from '../constants/productLanguage';
import React, { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppPageHeader, IconButton, SegmentedControl } from '../components/ui';
import { layout, spacing } from '../constants/theme';
import { HomeCloudFilesView } from './HomeCloudFilesScreen';
import { HomeCloudMemoriesView } from './HomeCloudMemoriesScreen';

type HomeCloudSection = 'files' | 'memories';

export function HomeCloudScreen() {
  const styles = useThemeStyles(createStylesForTheme);

  const navigation = useNavigation<any>();
  const [section, setSection] = useState<HomeCloudSection>('files');

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'left', 'right']}>
      <AppPageHeader
        title={productNames.files}
        leading={navigation.canGoBack() ? (
          <IconButton
            icon="chevron-back-outline"
            variant="plain"
            onPress={() => navigation.goBack()}
            accessibilityLabel="Volver a Más"
          />
        ) : undefined}
        style={styles.header}
      />
      <SegmentedControl
        selectionMode="single"
        value={section}
        options={[{ value: 'files', label: 'Archivos' }, { value: 'memories', label: 'Recuerdos' }]}
        onChange={setSection}
        accessibilityLabel="Secciones de Archivos"
        style={styles.selector}
      />
      <View style={styles.content}>
        <View style={[styles.pane, section !== 'files' && styles.hidden]} accessibilityElementsHidden={section !== 'files'}>
          <HomeCloudFilesView active={section === 'files'} />
        </View>
        <View style={[styles.pane, section !== 'memories' && styles.hidden]} accessibilityElementsHidden={section !== 'memories'}>
          <HomeCloudMemoriesView active={section === 'memories'} />
        </View>
      </View>
    </SafeAreaView>
  );
}



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background.base },
  header: { marginHorizontal: spacing[5], marginTop: layout.screen.topPadding },
  selector: { marginHorizontal: spacing[5], marginTop: spacing[2] },
  content: { flex: 1 },
  pane: { flex: 1 },
  hidden: { display: 'none' },
});
}
