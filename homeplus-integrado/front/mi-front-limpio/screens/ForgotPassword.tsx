
import { useThemeStyles } from '../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../constants/theme';
import React, { useEffect, useRef, useState } from 'react';
import { Animated, Keyboard, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AppLogo } from '../components/AppLogo';
import { AuthScreenLayout } from '../components/AuthScreenLayout';
import { AuthTextInput } from '../components/AuthTextInput';
import { AppButton, AppText } from '../components/ui';
import { layout, typography } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import type { AuthStackParamList } from '../navigation/types';
import { authErrorHaptic, authSuccessHaptic } from '../utils/haptics';

type Props = NativeStackScreenProps<AuthStackParamList, 'ForgotPassword'>;

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const getRecoveryErrorMessage = (message: string) => {
  const normalized = message.toLowerCase();

  if (
    normalized.includes('network')
    || normalized.includes('fetch')
    || normalized.includes('conectar')
    || normalized.includes('servidor')
  ) {
    return 'No pudimos conectarnos. Probá de nuevo en unos segundos.';
  }

  return 'No pudimos enviar el enlace. Revisa el correo e intenta nuevamente.';
};

export const ForgotPasswordScreen = ({ navigation }: Props) => {
  const styles = useThemeStyles(createStylesForTheme);

  const { resetPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const successScale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!successMessage) {
      return;
    }

    Animated.sequence([
      Animated.timing(successScale, {
        toValue: 1.03,
        duration: 120,
        useNativeDriver: true,
      }),
      Animated.timing(successScale, {
        toValue: 1,
        duration: 120,
        useNativeDriver: true,
      }),
    ]).start();
  }, [successMessage, successScale]);

  const clearMessages = () => {
    if (errorMessage) {
      setErrorMessage(null);
    }

    if (successMessage) {
      setSuccessMessage(null);
    }
  };

  const handleResetPassword = async () => {
    if (loading) {
      return;
    }

    Keyboard.dismiss();

    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setSuccessMessage(null);
      void authErrorHaptic();
      setErrorMessage('Ingresa tu correo para recuperar el acceso.');
      return;
    }

    if (!EMAIL_REGEX.test(trimmedEmail)) {
      setSuccessMessage(null);
      void authErrorHaptic();
      setErrorMessage('Ingresá un correo válido.');
      return;
    }

    setLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const result = await resetPassword(trimmedEmail);

      if (result.error) {
        void authErrorHaptic();
        setErrorMessage(getRecoveryErrorMessage(result.error));
      } else {
        void authSuccessHaptic();
        setSuccessMessage('Si el correo está registrado, te enviamos un enlace para recuperar tu acceso.');
      }
    } catch {
      void authErrorHaptic();
      setErrorMessage('No pudimos conectarnos. Probá de nuevo en unos segundos.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthScreenLayout screenIndicator="AUTH - RECOVERY" centerContent presentation="premium">
      <View style={styles.header}>
        <AppLogo size={70} rounded style={styles.logo} />
        <AppText variant="title1" style={styles.title}>Recuperá tu acceso</AppText>
        <AppText variant="bodySmall" tone="secondary" style={styles.subtitle}>
          Te vamos a enviar un enlace seguro para volver a entrar a tu hogar.
        </AppText>
      </View>

      <View style={styles.form}>
        <AuthTextInput
          label="Email"
          placeholder="tu@email.com"
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          textContentType="emailAddress"
          returnKeyType="done"
          editable={!loading}
          value={email}
          onChangeText={(value) => {
            clearMessages();
            setEmail(value);
          }}
          onSubmitEditing={() => void handleResetPassword()}
        />

        {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}
        {successMessage ? (
          <Animated.View style={{ transform: [{ scale: successScale }] }}>
            <Text style={styles.successText}>{successMessage}</Text>
          </Animated.View>
        ) : null}

        <AppButton
          title={loading ? 'Enviando…' : 'Enviar enlace'}
          loading={loading}
          style={styles.primaryButton}
          onPress={() => void handleResetPassword()}
          disabled={loading}
          accessibilityLabel="Enviar enlace de recuperación"
        />

        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => navigation.navigate('Login')}
          disabled={loading}
          accessibilityRole="button"
          accessibilityLabel="Volver al login"
        >
          <Text style={styles.linkText}>Volver a iniciar sesión</Text>
        </TouchableOpacity>
      </View>
    </AuthScreenLayout>
  );
};



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  header: { alignItems: 'center', marginBottom: layout.stack.section },
  logo: { marginBottom: layout.stack.content },
  title: { color: colors.text.primary, marginBottom: layout.stack.related, textAlign: 'center' },
  subtitle: { textAlign: 'center', maxWidth: 350 },
  form: { width: '100%' },
  errorText: {
    color: '#A85050',
    fontSize: 13,
    marginBottom: 12,
    lineHeight: 18,
    backgroundColor: '#F5E2E2',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  successText: {
    color: '#558563',
    fontSize: 13,
    marginBottom: 12,
    lineHeight: 18,
    backgroundColor: '#E1EFE5',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  primaryButton: {
    width: '100%',
    marginTop: 8,
  },
  linkButton: { marginTop: 24, alignItems: 'center' },
  linkText: { color: colors.brandPressed, ...typography.bodySmall, fontWeight: '700' },
});
}
