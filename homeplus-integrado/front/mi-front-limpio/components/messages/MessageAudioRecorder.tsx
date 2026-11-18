
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useState } from 'react';
import { Linking, Pressable, StyleSheet, View } from 'react-native';
import { RecordingPresets, requestRecordingPermissionsAsync, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from 'expo-audio';
import * as FileSystem from 'expo-file-system/legacy';
import { AppText } from '../ui';
import { radius, spacing } from '../../constants/theme';
import type { LocalMessageMedia } from '../../services/richMessagingMedia';

const clock = (ms: number) => `${Math.floor(ms / 60000).toString().padStart(2, '0')}:${Math.floor((ms % 60000) / 1000).toString().padStart(2, '0')}`;

export function MessageAudioRecorder({ onReady, onCancel }: { onReady: (media: LocalMessageMedia) => void; onCancel: () => void }) {
  const styles = useThemeStyles(createStylesForTheme);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder, 200);
  const [phase, setPhase] = useState<'idle' | 'recording' | 'error' | 'denied'>('idle');
  const [canAskAgain, setCanAskAgain] = useState(true);
  const start = async () => {
    const permission = await requestRecordingPermissionsAsync(); setCanAskAgain(permission.canAskAgain);
    if (!permission.granted) { setPhase('denied'); return; }
    try { await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true }); await recorder.prepareToRecordAsync(); recorder.record(); setPhase('recording'); }
    catch { setPhase('error'); }
  };
  const stop = async () => {
    try {
      await recorder.stop(); await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      const uri = recorder.uri ?? recorder.getStatus().url; const durationMs = recorder.getStatus().durationMillis;
      const info = uri ? await FileSystem.getInfoAsync(uri) : null;
      if (!uri || !info?.exists || !info.size || durationMs < 200) throw new Error('audio_empty');
      onReady({ uri, kind: 'audio', mimeType: 'audio/mp4', originalName: `audio-${Date.now()}.m4a`, sizeBytes: info.size, durationMs });
    } catch { setPhase('error'); }
  };
  return <View style={styles.box} testID="messages.attach.audio.recorder">
    <AppText variant="title3">Audio para tu hogar</AppText><AppText tone="secondary">{phase === 'recording' ? `Grabando ${clock(state.durationMillis)}` : 'Grabá una nota de voz y revisala antes de enviar.'}</AppText>
    {phase === 'denied' ? <><AppText tone="danger">Necesitamos el micrófono para grabar.</AppText><Pressable onPress={() => canAskAgain ? void start() : void Linking.openSettings()} style={styles.button}><AppText tone="inverse" weight="800">{canAskAgain ? 'Permitir micrófono' : 'Abrir configuración'}</AppText></Pressable></> : null}
    {phase === 'error' ? <AppText tone="danger">No pudimos preparar el audio. Intentá de nuevo.</AppText> : null}
    {phase === 'recording' ? <Pressable testID="messages.attach.audio.stop" onPress={() => void stop()} style={[styles.button, styles.stop]} accessibilityLabel="Detener grabación"><AppText tone="inverse" weight="800">Detener y revisar</AppText></Pressable> : <Pressable testID="messages.attach.audio.start" onPress={() => void start()} style={styles.button} accessibilityLabel="Comenzar grabación"><AppText tone="inverse" weight="800">Grabar audio</AppText></Pressable>}
    <Pressable onPress={onCancel} accessibilityLabel="Cancelar audio"><AppText tone="secondary" weight="700">Cancelar</AppText></Pressable>
  </View>;
}


function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({ box: { gap: spacing[3], paddingVertical: spacing[3] }, button: { minHeight: 48, borderRadius: radius.lg, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing[3] }, stop: { backgroundColor: colors.danger?.base ?? colors.terracotta[600] } });
}
