
import { useThemeStyles } from '../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../constants/theme';
import React, { useRef, useState } from 'react';
import { Keyboard, Platform, StyleSheet, Text, TouchableOpacity, View, type TextInputInstance } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import * as AppleAuthentication from 'expo-apple-authentication';
import { AppLogo } from '../components/AppLogo';
import { AuthScreenLayout } from '../components/AuthScreenLayout';
import { AuthTextInput } from '../components/AuthTextInput';
import { AppButton, AppText } from '../components/ui';
import { layout, radius, typography } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import type { RootStackParamList } from '../navigation/types';
import { authErrorHaptic, authSuccessHaptic } from '../utils/haptics';
//import googleLogo from '../assets/google-logo.svg';

type Props = NativeStackScreenProps<RootStackParamList, 'Login'>;

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const getLoginErrorMessage = (message: string) => {
  const normalized = message.toLowerCase();

  if (
    normalized.includes('network')
    || normalized.includes('fetch')
    || normalized.includes('conectar')
    || normalized.includes('servidor')
  ) {
    return 'No pudimos conectarnos. Probá de nuevo en unos segundos.';
  }

  return 'No pudimos iniciar sesión. Revisá tu correo y contraseña.';
};

const getGoogleErrorMessage = (message: string) => {
  const normalized = message.toLowerCase();

  if (
    normalized.includes('network')
    || normalized.includes('fetch')
    || normalized.includes('conectar')
  ) {
    return 'No pudimos conectarnos. Probá de nuevo en unos segundos.';
  }

  if (
    normalized.includes('cancelled')
    || normalized.includes('cancel')
  ) {
    return null;
  }

  return 'No pudimos iniciar sesión con Google. Intentá nuevamente.';
};

export const LoginScreen = ({ navigation }: Props) => {
  const styles = useThemeStyles(createStylesForTheme);

  const { signIn, signInWithGoogle, signInWithApple } = useAuth();
  const passwordInputRef = useRef<TextInputInstance>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [appleLoading, setAppleLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [appleAvailable, setAppleAvailable] = useState(false);

  const clearError = () => {
    if (errorMessage) {
      setErrorMessage(null);
    }
  };

const submitLogin = async () => {
    if (loading) {
      return;
    }

    Keyboard.dismiss();

    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      void authErrorHaptic();
      setErrorMessage('Ingresá tu correo para continuar.');
      return;
    }

    if (!EMAIL_REGEX.test(trimmedEmail)) {
      void authErrorHaptic();
      setErrorMessage('Ingresá un correo válido.');
      return;
    }

    if (!password.trim()) {
      void authErrorHaptic();
      setErrorMessage('Ingresá tu contraseña para continuar.');
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    const result = await signIn({
      email: trimmedEmail,
      password,
    });

    if (result.error) {
      void authErrorHaptic();
      setErrorMessage(getLoginErrorMessage(result.error));
    } else {
      void authSuccessHaptic();
    }

    setLoading(false);
  };

  const handleGoogleSignIn = async () => {
    if (googleLoading) {
      return;
    }

    Keyboard.dismiss();
    setErrorMessage(null);
    setGoogleLoading(true);

    const result = await signInWithGoogle();

    if (result.error) {
      const errorMessage = getGoogleErrorMessage(result.error);
      if (errorMessage) {
        void authErrorHaptic();
        setErrorMessage(errorMessage);
      }
    }

    setGoogleLoading(false);
  };

  const handleAppleSignIn = async () => {
    if (appleLoading || !appleAvailable) {
      return;
    }

    Keyboard.dismiss();
    setErrorMessage(null);
    setAppleLoading(true);

    try {
      const result = await signInWithApple();

      if (result.error) {
        const normalized = result.error.toLowerCase();
        if (
          normalized.includes('dispositivo') ||
          normalized.includes('disponible') ||
          normalized.includes('solo')
        ) {
          setAppleAvailable(false);
        } else {
          void authErrorHaptic();
          setErrorMessage('No pudimos iniciar sesión con Apple. Probá de nuevo.');
        }
      }
    } finally {
      setAppleLoading(false);
    }
  };

  React.useEffect(() => {
    if (Platform.OS === 'ios') {
      void AppleAuthentication.isAvailableAsync().then((available) => {
        setAppleAvailable(available);
      }).catch(() => {
        setAppleAvailable(false);
      });
    }
  }, []);

  return (
    <AuthScreenLayout screenIndicator="01 - LOGIN" centerContent presentation="premium">
      <View style={styles.header}>
        <AppLogo size={70} rounded style={styles.logo} />
        <AppText variant="title1" style={styles.title}>Entrá a tu hogar</AppText>
        <AppText variant="bodySmall" tone="secondary" style={styles.subtitle}>Organizá tareas, compras, gastos y más desde un lugar compartido.</AppText>
      </View>

      <View style={styles.form}>
        <AuthTextInput
          testID="auth.email"
          label="Email"
          placeholder="tu@email.com"
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          textContentType="emailAddress"
          returnKeyType="next"
          blurOnSubmit={false}
          editable={!loading}
          value={email}
          onChangeText={(value) => {
            clearError();
            setEmail(value);
          }}
          onSubmitEditing={() => passwordInputRef.current?.focus()}
        />

        <AuthTextInput
          ref={passwordInputRef}
          testID="auth.password"
          label="Contraseña"
          placeholder="Tu contraseña"
          isPasswordField
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="password"
          textContentType="password"
          returnKeyType="done"
          editable={!loading}
          value={password}
          onChangeText={(value) => {
            clearError();
            setPassword(value);
          }}
          onSubmitEditing={() => void submitLogin()}
        />

        {errorMessage ? <AppText testID="auth.error" variant="bodySmall" tone="danger" style={styles.errorText} accessibilityLiveRegion="polite">{errorMessage}</AppText> : null}

        <AppButton
          title={loading ? 'Ingresando…' : 'Iniciar sesión'}
          loading={loading}
          style={styles.primaryButton}
          onPress={() => void submitLogin()}
          disabled={loading}
          testID="auth.submit"
          accessibilityLabel="Iniciar sesión"
        />

        <TouchableOpacity
          style={[styles.googleButton, googleLoading && styles.buttonDisabled]}
          onPress={() => void handleGoogleSignIn()}
          disabled={googleLoading || loading}
          accessibilityRole="button"
          accessibilityLabel="Continuar con Google"
        >
          <View style={styles.googleIcon}>
  <Text style={{ fontWeight: '800', fontSize: 16 }}>G</Text>
</View>
          <Text style={styles.googleButtonText}>
            {googleLoading ? 'Conectando con Google...' : 'Continuar con Google'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.forgotButton}
          onPress={() => navigation.navigate('ForgotPassword')}
          disabled={loading || googleLoading}
          accessibilityRole="button"
          accessibilityLabel="Recuperar contraseña"
        >
          <Text style={styles.forgotText}>Olvidé mi contraseña</Text>
</TouchableOpacity>

        {Platform.OS === 'ios' && appleAvailable ? (
          <TouchableOpacity
            style={[styles.appleButton, appleLoading && styles.buttonDisabled]}
            onPress={() => void handleAppleSignIn()}
            disabled={appleLoading || loading || googleLoading}
            accessibilityRole="button"
            accessibilityLabel="Continuar con Apple"
          >
            <View style={styles.appleButtonContent}>
              <AppleAuthentication.AppleAuthenticationButton
                buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
                buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
                cornerRadius={radius.button}
                style={styles.appleButtonNative}
                onPress={() => void handleAppleSignIn()}
              />
            </View>
          </TouchableOpacity>
        ) : null}

        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => navigation.navigate('P01Registro')}
          disabled={loading}
          accessibilityRole="button"
          accessibilityLabel="Ir a registro"
        >
          <Text style={styles.linkText}>¿No tenés cuenta? Creá tu espacio familiar</Text>
        </TouchableOpacity>
      </View>
    </AuthScreenLayout>
  );
};



function createStylesForTheme({ colors, shadows }: Pick<AppResolvedTheme, 'colors' | 'shadows'>) {
  return StyleSheet.create({
  header: { alignItems: 'center', marginBottom: layout.stack.section },
  logo: { marginBottom: layout.stack.content },
  title: { color: colors.text.primary, marginBottom: layout.stack.related, textAlign: 'center' },
  subtitle: { textAlign: 'center', maxWidth: 350 },
  form: { width: '100%' },
  errorText: {
    marginBottom: layout.stack.component,
    backgroundColor: colors.danger.soft,
    borderRadius: radius.md,
    paddingHorizontal: layout.stack.component,
    paddingVertical: layout.stack.component,
  },
  primaryButton: {
    width: '100%',
    marginTop: layout.stack.related,
  },
  buttonDisabled: { opacity: 0.6 },
  forgotButton: { marginTop: layout.stack.content, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  forgotText: { color: colors.text.secondary, ...typography.bodySmall, fontWeight: '600' },
  linkButton: { marginTop: layout.stack.section, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  linkText: { color: colors.brandPressed, ...typography.bodySmall, fontWeight: '700', textAlign: 'center' },
  googleButton: {
    backgroundColor: colors.surface.card,
    width: '100%',
    height: 52,
    borderRadius: radius.button,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 16,
    borderWidth: 1,
    borderColor: colors.border.default,
    ...shadows.shadow1,
    position: 'relative',
  },
  googleIcon: {
    position: 'absolute',
    left: 20,
    width: 20,
    height: 20,
  },
  googleButtonText: { color: colors.text.primary, fontSize: 15, fontWeight: '600' },
  appleButton: {
    width: '100%',
    marginTop: 16,
    alignItems: 'center',
  },
  appleButtonContent: {
    width: '100%',
    alignItems: 'center',
  },
  appleButtonNative: {
    width: '100%',
    height: 48,
  },
});
}
