import React, { useEffect, useRef } from 'react';
import { ActivityIndicator, Animated, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppLogo } from '../components/AppLogo';
import { AppText } from '../components/ui';
import { colors, layout, shadows } from '../constants/theme';

export const AuthLoadingScreen = () => {
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
        <AppLogo size={82} rounded style={styles.logo} />
        <AppText variant="title1" style={styles.title}>Preparando tu hogar…</AppText>
        <AppText variant="bodySmall" tone="secondary" style={styles.subtitle}>Estamos cargando tu espacio familiar.</AppText>
        <ActivityIndicator color={colors.brand} size="small" style={styles.loader} />
      </Animated.View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background.base },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: layout.screen.horizontalPaddingWide,
  },
  logo: {
    marginBottom: layout.stack.content,
    ...shadows.shadow2,
  },
  title: { color: colors.text.primary, marginBottom: layout.stack.related, textAlign: 'center' },
  subtitle: { textAlign: 'center' },
  loader: { marginTop: layout.stack.content },
});
