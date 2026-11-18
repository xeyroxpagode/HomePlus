import React, { useEffect, useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { AuthStackParamList } from '../navigation/types';
import { AppLogo } from '../components/AppLogo';
import { AppButton, AppText } from '../components/ui';
import { colors, layout, shadows } from '../constants/theme';

type Props = NativeStackScreenProps<AuthStackParamList, 'P00Splash'> & {
  loading?: boolean;
};

export const P00Splash = ({ navigation, loading = false }: Props) => {
  const fadeValue = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeValue, {
      toValue: 1,
      duration: 240,
      useNativeDriver: true,
    }).start();
  }, [fadeValue]);

  return (
    <SafeAreaView style={styles.container}>
      <Animated.View style={[styles.content, { opacity: fadeValue }]}>
        <View style={styles.iconContainer}>
          <AppLogo size={88} rounded style={styles.logo} />
        </View>
        
        <AppText variant="hero" style={styles.title}>HomePlus</AppText>
        <AppText variant="bodyLarge" tone="secondary" style={styles.subtitle}>
          {loading
            ? 'Estamos preparando tu hogar.'
            : 'Organizá la vida de tu casa en un solo lugar.'}
        </AppText>
        {loading ? (
          <View style={styles.loaderContainer}>
            <ActivityIndicator color={colors.brand} size="small" />
            <AppText variant="bodySmall" tone="tertiary" style={styles.loaderText}>Preparando tu hogar…</AppText>
          </View>
        ) : null}
      </Animated.View>

      <View style={styles.footer}>
        <AppButton
          title="Crear cuenta"
          style={styles.fullWidthButton}
          onPress={() => navigation?.navigate('P01Registro')}
          accessibilityLabel="Crear cuenta"
        />

        <AppButton
          title="Entrar a mi hogar"
          variant="secondary"
          style={styles.fullWidthButton}
          onPress={() => navigation.navigate('Login')}
          testID="auth.openLogin"
          accessibilityLabel="Entrar a mi hogar"
        />

        <AppText variant="caption" tone="tertiary" style={styles.disclaimer}>Privado, simple y pensado para tu familia.</AppText>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background.base },
  content: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: layout.screen.horizontalPaddingWide },
  iconContainer: { marginBottom: layout.stack.section },
  logo: {
    ...shadows.shadow2,
  },
  title: { color: colors.text.primary, marginBottom: layout.stack.related },
  subtitle: { textAlign: 'center', maxWidth: 340 },
  loaderContainer: { marginTop: layout.stack.content, alignItems: 'center' },
  loaderText: { marginTop: layout.stack.component },
  footer: { width: '100%', maxWidth: 480, alignSelf: 'center', paddingHorizontal: layout.screen.horizontalPaddingWide, paddingBottom: layout.screen.bottomPadding, alignItems: 'center', gap: layout.stack.component },
  fullWidthButton: { width: '100%' },
  disclaimer: { marginTop: layout.stack.related, textAlign: 'center' },
});
