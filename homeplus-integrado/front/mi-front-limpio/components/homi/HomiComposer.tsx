import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, StyleSheet, TextInput, View } from 'react-native';

import { AppText } from '../ui/AppText';
import { HomePlusIcon } from '../../constants/icons';
import type { HomiTheme } from './homiVisual';
import { homiSpacing, useHomiTheme } from './homiVisual';
import { HomiPressable } from './HomiPressable';

type AttachmentPreview = {
  uri: string;
  name: string;
  type: string;
  size?: number;
};

/**
 * The five voice states of DEMO V1. `uploading` and `processing` are the same
 * user facing state on purpose: the client cannot tell what the orchestrator
 * is doing with the audio, so it must not invent a distinction.
 */
export type HomiVoiceUiState =
  | 'idle'
  | 'recording'
  | 'uploading'
  | 'listening'
  | 'detecting_voice'
  | 'processing'
  | 'speaking'
  | 'interrupted'
  | 'error';

export const isVoiceListening = (state: HomiVoiceUiState): boolean =>
  state === 'recording' || state === 'listening' || state === 'detecting_voice';
export const isVoiceProcessing = (state: HomiVoiceUiState): boolean =>
  state === 'uploading' || state === 'processing';
export const isVoiceSpeaking = (state: HomiVoiceUiState): boolean => state === 'speaking';
export const isVoiceInterrupted = (state: HomiVoiceUiState): boolean =>
  state === 'interrupted';

type Props = {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  /** F01-A: abort the in-flight text request (HTTP only, never a write). */
  onCancelRequest?: () => void;
  disabled?: boolean;
  sending?: boolean;
  onAttachFile?: () => void;
  attachment?: AttachmentPreview | null;
  onRemoveAttachment?: () => void;
  uploading?: boolean;
  /** T30 - voice controls. */
  voiceState?: HomiVoiceUiState;
  voiceSupported?: boolean;
  /** The runtime cannot host the voice transport: the text channel stays open. */
  voiceUnavailable?: boolean;
  onVoicePress?: () => void;
  onVoiceCancel?: () => void;
  /** Real voice failure; the textual channel stays available. */
  voiceError?: string | null;
  /** HOMI V1: a transcript is sitting in the composer as an editable draft. */
  voiceDraft?: boolean;
  /** Discard only the draft, restoring the pre-dictation text. */
  onVoiceDraftDiscard?: () => void;
};

/**
 * Composer of the DEMO V1 conversation.
 *
 * One single surface: the field, the chips and the actions live inside the
 * same warm surface. There is no nested border around the text field (the
 * "orange box" of the previous implementation) and the surface carries no
 * elevation of its own.
 *
 * Every control keeps a real 44px touch target and an explicit accessibility
 * label; the focus indicator is never removed.
 */
export function HomiComposer({
  value,
  onChangeText,
  onSend,
  onCancelRequest,
  disabled,
  sending,
  onAttachFile,
  attachment,
  onRemoveAttachment,
  uploading,
  voiceState = 'idle',
  voiceSupported = false,
  voiceUnavailable = false,
  onVoicePress,
  onVoiceCancel,
  voiceError,
  voiceDraft = false,
  onVoiceDraftDiscard,
}: Props) {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  const listening = isVoiceListening(voiceState);
  const processing = isVoiceProcessing(voiceState);
  const speaking = isVoiceSpeaking(voiceState);
  const interrupted = isVoiceInterrupted(voiceState);
  const voiceActive = listening || processing || speaking || interrupted;
  const canSend = !disabled && !sending && !uploading && !voiceActive && value.trim().length > 0;
  const fieldDisabled = Boolean(disabled || sending || uploading || voiceActive);
  const [fieldFocused, setFieldFocused] = useState(false);

  const handleSend = useCallback(() => {
    if (canSend) onSend();
  }, [canSend, onSend]);

  const voiceLabel = (() => {
    switch (voiceState) {
      case 'recording':
        return 'Detener la grabación y transcribir';
      case 'listening':
        return 'Escuchando';
      case 'detecting_voice':
        return 'Detectando tu voz';
      case 'uploading':
      case 'processing':
        return 'Transcribiendo el audio';
      case 'speaking':
        return 'Homi está hablando; podés interrumpirla';
      case 'interrupted':
        return 'Interrumpida; te escucho de nuevo';
      case 'error':
        return 'Reintentar el dictado';
      default:
        return 'Grabar y transcribir un mensaje';
    }
  })();

  // The reference implementation keeps the icon controls flat: no background
  // of their own, no border. The warm surface they sit on is the surface.

  return (
    <View style={styles.root}>
      {attachment ? (
        <View style={styles.attachmentChip}>
          <HomePlusIcon
            name={attachment.type.startsWith('image/') ? 'image-outline' : 'document-text-outline'}
            size={18}
            color={theme.colors.text.secondary}
          />
          <View style={styles.attachmentBody}>
            <AppText variant="caption" weight="700" numberOfLines={1}>
              {attachment.name}
            </AppText>
            <AppText variant="caption" tone="tertiary">
              {attachment.type}
              {attachment.size ? ` · ${(attachment.size / 1024).toFixed(1)} KB` : ''}
            </AppText>
          </View>
          {onRemoveAttachment ? (
            <HomiPressable
              onPress={onRemoveAttachment}
              disabled={uploading}
              accessibilityLabel="Quitar el adjunto"
              style={styles.chipAction}
            >
              <HomePlusIcon name="close" size={16} color={theme.colors.text.tertiary} />
            </HomiPressable>
          ) : null}
        </View>
      ) : null}

      <TextInput
        style={[styles.input, fieldFocused && !fieldDisabled ? styles.inputFocused : null]}
        value={value}
        onChangeText={onChangeText}
        onFocus={() => setFieldFocused(true)}
        onBlur={() => setFieldFocused(false)}
        placeholder={
          voiceState === 'recording'
            ? 'Grabando… tocá el micrófono para detener'
            : voiceState === 'uploading' || voiceState === 'processing'
              ? 'Transcribiendo lo que dijiste…'
              : listening
                ? voiceState === 'detecting_voice'
                  ? 'Detectando tu voz…'
                  : 'Te escucho…'
                : interrupted
                  ? 'Te escucho de nuevo…'
                  : attachment
                    ? 'Añadí un mensaje (opcional)…'
                    : 'Preguntale algo a Homi'
        }
        placeholderTextColor={theme.colors.text.muted}
        editable={!fieldDisabled}
        multiline
        accessibilityLabel="Preguntale algo a Homi"
        accessibilityHint="Escribí un mensaje para Homi; Enter inserta una nueva línea"
        returnKeyType="send"
        onSubmitEditing={handleSend}
        blurOnSubmit={false}
        selectionColor={theme.colors.terracotta[700]}
      />

      {voiceActive ? (
        <View style={styles.voiceRow}>
          <View style={styles.voiceState}>
            {processing ? (
              <ActivityIndicator size="small" color={theme.colors.terracotta[700]} />
            ) : (
              <HomePlusIcon
                name={listening || interrupted ? 'mic' : 'volume-high-outline'}
                size={18}
                color={
                  listening || interrupted
                    ? theme.colors.brand
                    : theme.colors.terracotta[700]
                }
              />
            )}
            <AppText variant="bodySmall" weight="600" tone="secondary" style={styles.voiceLabel}>
              {voiceState === 'recording'
                ? 'Grabando…'
                : processing
                  ? 'Transcribiendo lo que dijiste…'
                  : 'Escuchando…'}
            </AppText>
          </View>

          <View style={styles.voiceActions}>
            {listening && onVoiceCancel ? (
              <HomiPressable
                onPress={onVoiceCancel}
                disabled={disabled}
                accessibilityLabel="Cancelar la grabación"
                style={styles.voiceGhost}
              >
                <AppText variant="caption" weight="700" tone="tertiary">
                  Cancelar
                </AppText>
              </HomiPressable>
            ) : null}

            {voiceState === 'recording' && onVoicePress ? (
              <HomiPressable
                onPress={onVoicePress}
                disabled={disabled}
                accessibilityLabel="Detener la grabación y transcribir"
                accessibilityHint="Envía el audio solo a transcripción; no envía un mensaje"
                style={styles.voiceSend}
              >
                <AppText variant="caption" weight="700" tone="inverse">
                  Detener
                </AppText>
              </HomiPressable>
            ) : null}
          </View>
        </View>
      ) : (
        <View style={styles.actions}>
          {onAttachFile ? (
            <HomiPressable
              onPress={onAttachFile}
              disabled={Boolean(disabled || sending || !!attachment)}
              accessibilityLabel="Adjuntar un archivo"
              accessibilityHint="Abre el selector de documentos e imágenes"
              style={styles.iconAction}
            >
              <HomePlusIcon name="attach-outline" size={20} color={theme.colors.text.secondary} />
            </HomiPressable>
          ) : null}

          {voiceSupported && onVoicePress ? (
            <HomiPressable
              onPress={onVoicePress}
              disabled={Boolean(disabled || sending || uploading)}
              accessibilityLabel={voiceLabel}
              accessibilityHint="Grabá lo que querés decir; se transcribe como borrador editable y lo enviás con Enviar"
              style={[styles.iconAction, voiceError && styles.iconActionError]}
            >
              <HomePlusIcon
                name={voiceError ? 'refresh' : 'mic-outline'}
                size={20}
                color={voiceError ? theme.colors.brand : theme.colors.text.secondary}
              />
            </HomiPressable>
          ) : null}

          <View style={styles.sendSlot}>
            {sending && onCancelRequest ? (
              <HomiPressable
                onPress={onCancelRequest}
                accessibilityLabel="Detener la solicitud en curso"
                accessibilityHint="Detiene la espera de la respuesta; no revierte ninguna escritura ya confirmada"
                style={styles.voiceGhost}
              >
                <AppText variant="bodySmall" weight="700" tone="tertiary">
                  Detener
                </AppText>
              </HomiPressable>
            ) : null}
            <HomiPressable
              onPress={handleSend}
              disabled={!canSend || sending}
              accessibilityLabel="Enviar el mensaje"
              accessibilityState={{ disabled: !canSend || sending, busy: Boolean(sending) }}
              style={[styles.send, (!canSend || sending) && styles.sendDisabled]}
            >
              {sending ? (
                <ActivityIndicator size="small" color={theme.colors.text.inverse} />
              ) : (
                <HomePlusIcon name="send" size={18} color={theme.colors.text.inverse} />
              )}
              <AppText variant="bodySmall" weight="700" tone="inverse">
                {sending ? 'Enviando…' : 'Enviar'}
              </AppText>
            </HomiPressable>
          </View>
        </View>
      )}

      {voiceDraft ? (
        <View style={styles.attachmentChip}>
          <HomePlusIcon name="create-outline" size={14} color={theme.colors.brand} />
          <AppText variant="caption" tone="secondary" style={styles.voiceFallbackText}>
            Borrador transcrito: editá lo que quieras y tocá Enviar cuando estés listo. Homi todavía no recibió nada.
          </AppText>
          {onVoiceDraftDiscard ? (
            <HomiPressable
              onPress={onVoiceDraftDiscard}
              accessibilityLabel="Descartar el borrador transcrito"
              style={styles.chipAction}
            >
              <AppText variant="caption" weight="700" tone="tertiary">
                Descartar
              </AppText>
            </HomiPressable>
          ) : null}
        </View>
      ) : null}

      {voiceUnavailable && !voiceError ? (
        <View style={styles.voiceFallback}>
          <HomePlusIcon name="mic-off-outline" size={14} color={theme.colors.text.tertiary} />
          <AppText variant="caption" tone="tertiary" style={styles.voiceFallbackText}>
            Voz no disponible en esta sesión: continuá por texto.
          </AppText>
        </View>
      ) : null}

      {voiceError ? (
        <View style={styles.voiceFallback}>
          <HomePlusIcon name="alert-circle-outline" size={14} color={theme.colors.danger.base} />
          <AppText variant="caption" tone="danger" style={styles.voiceFallbackText}>
            {voiceError} Voz no disponible: continuá por texto.
          </AppText>
        </View>
      ) : null}
    </View>
  );
}

const makeStyles = (theme: HomiTheme) =>
  StyleSheet.create({
    root: {
      marginHorizontal: theme.spacing[4],
      padding: homiSpacing.intraTurn,
      borderRadius: theme.radius.xl,
      backgroundColor: theme.colors.background.soft,
      gap: homiSpacing.intraTurn,
    },
    attachmentChip: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.rowGap,
      padding: homiSpacing.rowGap,
      borderRadius: theme.radius.md,
      backgroundColor: theme.colors.background.alt,
    },
    attachmentBody: {
      flex: 1,
    },
    chipAction: {
      width: theme.touchTargets.normal,
      height: theme.touchTargets.normal,
      alignItems: 'center',
      justifyContent: 'center',
    },
    input: {
      minHeight: 56,
      maxHeight: 156,
      paddingHorizontal: theme.spacing[2],
      paddingVertical: theme.spacing[2],
      color: theme.colors.text.primary,
      fontSize: 16,
      lineHeight: 22,
      // The browser would otherwise draw its default focus ring (a dark box)
      // on top of the single-surface composer. The accessible indicator is
      // `inputFocused` below instead (target "focus-quiet": bottom border).
      outlineColor: 'transparent',
      outlineOffset: 0,
      outlineStyle: 'solid',
      outlineWidth: 0,
      borderBottomWidth: 1.5,
      borderBottomColor: 'transparent',
      borderBottomLeftRadius: 0,
      borderBottomRightRadius: 0,
    },
    inputFocused: {
      borderBottomColor: theme.colors.terracotta[700],
    },
    actions: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.rowGap,
    },
    iconAction: {
      width: theme.touchTargets.normal,
      height: theme.touchTargets.normal,
      borderRadius: theme.radius.full,
      alignItems: 'center',
      justifyContent: 'center',
    },
    iconActionError: {
      backgroundColor: theme.colors.danger.soft,
    },
    sendSlot: {
      flex: 1,
      flexDirection: 'row',
      justifyContent: 'flex-end',
    },
    send: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.rowGap,
      minHeight: theme.touchTargets.normal,
      paddingHorizontal: theme.spacing[4],
      borderRadius: theme.radius.button,
      backgroundColor: theme.colors.terracotta[700],
    },
    sendDisabled: {
      opacity: 0.45,
    },
    voiceRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: homiSpacing.rowGap,
      paddingVertical: theme.spacing[1],
    },
    voiceState: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.rowGap,
      flexShrink: 1,
    },
    voiceLabel: {
      flexShrink: 1,
    },
    voiceActions: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.rowGap,
    },
    voiceGhost: {
      minHeight: theme.touchTargets.normal,
      justifyContent: 'center',
      paddingHorizontal: theme.spacing[2],
    },
    voiceSend: {
      minHeight: theme.touchTargets.normal,
      justifyContent: 'center',
      paddingHorizontal: theme.spacing[3],
      borderRadius: theme.radius.button,
      backgroundColor: theme.colors.terracotta[700],
    },
    voiceFallback: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 4,
    },
    voiceFallbackText: {
      flex: 1,
    },
  });
