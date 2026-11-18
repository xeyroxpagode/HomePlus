
import { useThemeStyles } from '../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../constants/theme';

import React, { useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AuthScreenLayout } from '../components/AuthScreenLayout';
import { AppLogo } from '../components/AppLogo';
import { useAuth } from '../context/AuthContext';
import { createHousehold } from '../services/households';
import type { PrivateStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<PrivateStackParamList, 'P02CrearGrupo'>;

type FamilyType = 'nucleo' | 'con_abuelos' | 'separados' | 'otro';

const FAMILY_TYPES: { id: FamilyType; icon: string; label: string }[] = [
  { id: 'nucleo',      icon: '👨‍👩‍👧‍👦', label: 'Núcleo' },
  { id: 'con_abuelos', icon: '🏡',      label: 'Con abuelos' },
  { id: 'separados',   icon: '🏘️',      label: 'Separados' },
  { id: 'otro',        icon: '✨',       label: 'Otro' },
];

const extractJoinToken = (value: string) => {
  const trimmed = value.trim();

  if (!trimmed) return '';

  const tokenMatch = trimmed.match(/[?&]token=([^&#]+)/);
  if (tokenMatch?.[1]) {
    return decodeURIComponent(tokenMatch[1]).trim();
  }

  return trimmed;
};

export const P02CrearGrupo = ({ navigation }: Props) => {
  const styles = useThemeStyles(createStylesForTheme);

  const { session, user, signOut, refetchMe } = useAuth();
  const [nombreHogar, setNombreHogar] = useState('');
  const [joinToken, setJoinToken] = useState('');
  const [tipoFamilia, setTipoFamilia] = useState<FamilyType>('nucleo');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [focusedInput, setFocusedInput] = useState<'household' | 'join' | null>(null);

const handleCreate = async () => {
    Keyboard.dismiss();

    if (!nombreHogar.trim()) {
      setErrorMessage('Escribe un nombre para tu hogar antes de continuar.');
      return;
    }

    const accessToken = session?.access_token;

    if (!accessToken) {
      setErrorMessage('Tu sesion vencio. Volvé a iniciar sesion.');
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    const { household, error } = await createHousehold(accessToken, nombreHogar);

    if (error || !household) {
      setErrorMessage(error ?? 'Error inesperado. Intenta nuevamente.');
      setLoading(false);
      return;
    }

    await refetchMe();

    setLoading(false);
  };

const handleSignOut = async () => {
    await signOut();
  };

  const handleJoin = () => {
    Keyboard.dismiss();
    const token = extractJoinToken(joinToken);

    if (!token) {
      setErrorMessage('Pegá el link o token de invitación para unirte.');
      return;
    }

    setErrorMessage(null);
    navigation.navigate('JoinHousehold', { token });
  };

return (
    <AuthScreenLayout screenIndicator="02 - CREAR GRUPO" dismissKeyboardOnTapOutside={false}>
            <View style={styles.inner}>
              <View style={styles.topBar}>
                <Text style={styles.userEmail} numberOfLines={1}>{user?.email ?? ''}</Text>
                <TouchableOpacity onPress={() => void handleSignOut()} accessibilityRole="button">
                  <Text style={styles.logoutText}>Cerrar sesión</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.header}>
                <AppLogo size={40} rounded />
                <Text style={styles.title}>Nombra tu hogar</Text>
                <Text style={styles.subtitle}>
                  Este será el espacio privado de tu familia.{'\n'}Solo las personas que invites pueden entrar.
                </Text>
              </View>

<View style={styles.form}>
                <TextInput
                  style={[
                    styles.input,
                    focusedInput === 'household' ? styles.inputFocused : null,
                    errorMessage && !nombreHogar.trim() ? styles.inputError : null,
                    loading ? styles.inputDisabled : null,
                  ]}
                  placeholder="Familia García"
                  placeholderTextColor="#746D66"
                  returnKeyType="done"
                  editable={!loading}
                  value={nombreHogar}
                  onFocus={() => setFocusedInput('household')}
                  onBlur={() => setFocusedInput(null)}
                  onChangeText={(v) => { setErrorMessage(null); setNombreHogar(v); }}
                  onSubmitEditing={() => void handleCreate()}
                />

                <Text style={styles.label}>¿Qué describe mejor a tu familia?</Text>

                <View style={styles.pillsContainer}>
                  {FAMILY_TYPES.map(({ id, icon, label }) => (
                    <TouchableOpacity
                      key={id}
                      style={[styles.pill, tipoFamilia === id && styles.pillSelected]}
                      onPress={() => setTipoFamilia(id)}
                      disabled={loading}
                    >
                      <Text style={styles.pillText}>{icon} {label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}

                <TouchableOpacity
                  style={[styles.primaryButton, loading && styles.buttonDisabled]}
                  onPress={() => void handleCreate()}
                  disabled={loading}
                  accessibilityRole="button"
                  accessibilityLabel="Crear hogar"
                >
                  {loading
                    ? <ActivityIndicator color="#FFFFFF" />
                    : <Text style={styles.primaryButtonText}>Crear hogar</Text>
                  }
                </TouchableOpacity>

                <View style={styles.separator}>
                  <View style={styles.separatorLine} />
                  <Text style={styles.separatorText}>o</Text>
                  <View style={styles.separatorLine} />
                </View>

                <Text style={styles.label}>Unirte a un hogar existente</Text>
                <TextInput
                  style={[
                    styles.input,
                    focusedInput === 'join' ? styles.inputFocused : null,
                    errorMessage && !joinToken.trim() && nombreHogar.trim() ? styles.inputError : null,
                    loading ? styles.inputDisabled : null,
                  ]}
                  placeholder="Pegá acá tu link o token"
                  placeholderTextColor="#746D66"
                  autoCapitalize="none"
                  autoCorrect={false}
                  returnKeyType="done"
                  editable={!loading}
                  value={joinToken}
                  onFocus={() => setFocusedInput('join')}
                  onBlur={() => setFocusedInput(null)}
                  onChangeText={(v) => { setErrorMessage(null); setJoinToken(v); }}
                  onSubmitEditing={handleJoin}
                />

                <TouchableOpacity
                  style={[styles.secondaryButton, loading && styles.buttonDisabled]}
                  onPress={handleJoin}
                  disabled={loading}
                  accessibilityRole="button"
                  accessibilityLabel="Unirme con invitación"
                >
                  <Text style={styles.secondaryButtonText}>Unirme con invitación</Text>
</TouchableOpacity>
              </View>
            </View>
    </AuthScreenLayout>
  );
};



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  inner: { width: '100%' },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  userEmail: { fontSize: 12, color: colors.text.secondary, flex: 1, marginRight: 12 },
  logoutText: { color: colors.brand, fontSize: 13, fontWeight: '600' },
  header: { alignItems: 'center', marginBottom: 32 },
  title: { fontSize: 26, fontWeight: '700', color: colors.text.primary, marginBottom: 8 },
  subtitle: { fontSize: 14, color: colors.text.secondary, textAlign: 'center', lineHeight: 22 },
  form: { width: '100%' },
  input: {
    backgroundColor: colors.surface.card,
    borderWidth: 1,
    borderColor: colors.border.default,
    borderRadius: 12,
    minHeight: 56,
    paddingHorizontal: 16,
    paddingVertical: 14,
    color: colors.text.primary,
    marginBottom: 32,
    fontSize: 16,
  },
  inputFocused: {
    borderColor: colors.brand,
    backgroundColor: colors.surface.card,
  },
  inputError: {
    borderColor: '#C46B6B',
  },
  inputDisabled: {
    backgroundColor: '#F3F0EB',
    borderColor: '#D8D1C8',
    color: colors.text.tertiary,
  },
  label: { fontSize: 14, color: colors.text.primary, fontWeight: '500', marginBottom: 16 },
  pillsContainer: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 40 },
  pill: {
    backgroundColor: colors.surface.card,
    borderWidth: 1,
    borderColor: colors.border.default,
    borderRadius: 24,
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  pillSelected: { backgroundColor: colors.brandSoft, borderColor: colors.brand },
  pillText: { fontSize: 14, color: colors.text.primary, fontWeight: '500' },
  errorText: { color: colors.danger.text, fontSize: 13, marginBottom: 16, lineHeight: 18 },
  primaryButton: {
    backgroundColor: colors.brand,
    width: '100%',
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 52,
  },
  primaryButtonText: { color: colors.text.inverse, fontSize: 16, fontWeight: '600' },
  separator: { flexDirection: 'row', alignItems: 'center', marginVertical: 24 },
  separatorLine: { flex: 1, height: 1, backgroundColor: colors.border.subtle },
  separatorText: { marginHorizontal: 14, color: '#888888', fontSize: 13, fontWeight: '600' },
  secondaryButton: {
    backgroundColor: colors.surface.card,
    width: '100%',
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 52,
    borderWidth: 1.5,
    borderColor: colors.brand,
  },
  secondaryButtonText: { color: colors.brand, fontSize: 16, fontWeight: '700' },
  buttonDisabled: { opacity: 0.6 },
});
}
