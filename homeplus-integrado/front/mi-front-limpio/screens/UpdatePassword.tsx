
import { useThemeStyles } from '../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../constants/theme';
import React, { useEffect, useRef, useState } from 'react';
import { Animated, Keyboard, StyleSheet, Text, View, type TextInputInstance } from 'react-native';
import { AppLogo } from '../components/AppLogo';
import { AuthScreenLayout } from '../components/AuthScreenLayout';
import { AuthTextInput } from '../components/AuthTextInput';
import { AppButton, AppText } from '../components/ui';
import { layout } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import { authErrorHaptic, authSuccessHaptic } from '../utils/haptics';

export const UpdatePasswordScreen = () => {
  const styles = useThemeStyles(createStylesForTheme);

  const { updatePassword } = useAuth();
  const confirmPasswordInputRef = useRef<TextInputInstance>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
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

  const handleUpdatePassword = async () => {
    if (loading) {
      return;
    }

    Keyboard.dismiss();

    if (!password.trim()) {
      setSuccessMessage(null);
      void authErrorHaptic();
      setErrorMessage('Ingresá una nueva contraseña.');
      return;
    }

    if (password.length < 6) {
      setSuccessMessage(null);
      void authErrorHaptic();
      setErrorMessage('La contraseña necesita al menos 6 caracteres.');
      return;
    }

    if (password !== confirmPassword) {
      setSuccessMessage(null);
      void authErrorHaptic();
      setErrorMessage('Las contraseñas no coinciden.');
      return;
    }

    setLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    const result = await updatePassword(password);

    if (result.error) {
      void authErrorHaptic();
      setErrorMessage('No pudimos actualizar tu contraseña. Solicitá un nuevo enlace e intentá nuevamente.');
    } else {
      void authSuccessHaptic();
      setSuccessMessage('Contraseña actualizada.');
      setPassword('');
      setConfirmPassword('');
    }

    setLoading(false);
  };

  return (
    <AuthScreenLayout screenIndicator="AUTH - UPDATE PASSWORD" centerContent presentation="premium">
      <View style={styles.header}>
        <AppLogo size={70} rounded style={styles.logo} />
        <AppText variant="title1" style={styles.title}>Nueva contraseña</AppText>
        <AppText variant="bodySmall" tone="secondary" style={styles.subtitle}>
          Elegí una clave nueva para volver a entrar a tu hogar.
        </AppText>
      </View>

      <View style={styles.form}>
        <AuthTextInput
          label="Nueva contraseña"
          placeholder="Mínimo 6 caracteres"
          isPasswordField
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="new-password"
          textContentType="newPassword"
          returnKeyType="next"
          blurOnSubmit={false}
          editable={!loading}
          value={password}
          onChangeText={(value) => {
            clearMessages();
            setPassword(value);
          }}
          onSubmitEditing={() => confirmPasswordInputRef.current?.focus()}
        />

        <AuthTextInput
          ref={confirmPasswordInputRef}
          label="Confirmar contraseña"
          placeholder="Repetí tu nueva contraseña"
          isPasswordField
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="new-password"
          textContentType="newPassword"
          returnKeyType="done"
          editable={!loading}
          value={confirmPassword}
          onChangeText={(value) => {
            clearMessages();
            setConfirmPassword(value);
          }}
          onSubmitEditing={() => void handleUpdatePassword()}
        />

        {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}
        {successMessage ? (
          <Animated.View style={{ transform: [{ scale: successScale }] }}>
            <Text style={styles.successText}>{successMessage}</Text>
          </Animated.View>
        ) : null}

        <AppButton
          title={loading ? 'Actualizando…' : 'Guardar contraseña'}
          loading={loading}
          style={styles.primaryButton}
          onPress={() => void handleUpdatePassword()}
          disabled={loading}
          accessibilityLabel="Guardar nueva contraseña"
        />
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
});
}
