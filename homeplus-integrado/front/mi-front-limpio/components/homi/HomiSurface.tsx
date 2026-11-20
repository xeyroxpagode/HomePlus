import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';

import { AppText } from '../ui/AppText';
import { ErrorState } from '../ui/ErrorState';
import { HomePlusIcon } from '../../constants/icons';
import { useAuth } from '../../context/AuthContext';
import { HomiComposer, type HomiVoiceUiState } from './HomiComposer';
import {
  HOMI_DEMO_SUGGESTIONS,
  HomiEmptyState,
  type HomiSuggestion,
} from './HomiEmptyState';
import { HomiMessageList } from './HomiMessageList';
import { HomiPressable } from './HomiPressable';
import { homiSpacing, useHomiTheme } from './homiVisual';
import { invokeHomi } from '../../services/homi/homiClient';
import { createHomiMessage, type HomiMessage, type HomiToolResult } from '../../services/homi/homiMessages';
import { readPlannerTasks } from '../../services/homi/homiToolClient';
import {
  uploadAttachment,
  deleteAttachment,
  homiHealthCheck,
  HOMI_CONFIGURED,
} from '../../services/homi/homiAttachments';
import { ApiError, AbortError } from '../../services/api';
import { createHomiVoiceTransport } from '../../src/voice/createHomiVoiceTransport';
import { HomiVoiceError } from '../../src/voice/homiVoiceTransport';
import type { HomiVoiceTransport } from '../../src/voice/homiVoiceTransport';
import { homiTurnReducer } from '../../services/homi/homiTurnState';

const generateConversationId = (): string => {
  const random = Math.random().toString(36).slice(2, 10);
  return `conv_${Date.now().toString(36)}_${random}`;
};

const generateTurnId = (): string => {
  const random = Math.random().toString(36).slice(2, 10);
  return `turn_${Date.now().toString(36)}_${random}`;
};

const nowIso = (): string => new Date().toISOString();

const MIME_BY_EXTENSION: Record<string, string> = {
  pdf: 'application/pdf',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  heic: 'image/heic',
  txt: 'text/plain',
  md: 'text/markdown',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};

/** Derives a trustworthy MIME from the file name. No generic fallback. */
const inferMimeFromName = (name: string): string | null => {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  return MIME_BY_EXTENSION[ext] ?? null;
};

/**
 * iOS photo libraries can hand out `ph://` assets and Android `content://`
 * URIs that the native XHR FormData bridge cannot read. Stage a real `file://`
 * copy before uploading. `file://` results are already usable as-is.
 */
const stageAttachmentUri = async (uri: string, suggestedName: string): Promise<string> => {
  if (uri.startsWith('file://')) return uri;
  const FileSystem = await import('expo-file-system/legacy');
  const directory = `${FileSystem.cacheDirectory}homi-attachments`;
  const info = await FileSystem.getInfoAsync(directory);
  if (!info.exists) {
    await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
  }
  const safeName = suggestedName.replace(/[^a-zA-Z0-9._-]/g, '_') || 'archivo';
  const target = `${directory}/${Date.now()}_${safeName}`;
  await FileSystem.copyAsync({ from: uri, to: target });
  return target;
};

type SelectedAttachment = {
  uri: string;
  name: string;
  type: string;
  size?: number;
  /** Only set when the MIME was inferred from a trusted extension. */
  declaredMime?: string;
} | null;

type UploadedAttachment = {
  attachment_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes?: number;
};

type PendingTurn = {
  text: string;
  attachment: UploadedAttachment | null;
};

/**
 * Homi surface of the DEMO V1 closure.
 *
 * It connects the conversation, the Planner READ and the voice channel to the
 * contracts that actually exist. All Homi traffic goes through the
 * authenticated T07 gateway; the client never calls HOMI-D directly:
 *
 *   conversation  POST /api/homi/v1/text/turn       (T07 gateway -> HOMI-D)
 *   Planner READ  POST /api/homi/v1/tools/planner.tasks.list/invoke  (T07)
 *   attachments   POST/GET/DELETE /api/homi/v1/attachments/*  (T07 gateway -> HOMI-D)
 *   dictation     POST /api/homi/v1/voice/transcript (T07 gateway -> HOMI-C STT)
 *
 * HOMI V1 voice (Actor A): manual recording -> STT-only transcript ->
 * editable draft -> manual text send. No continuous listening, no VAD,
 * no barge-in, no TTS and no automatic message. T31 / Turn Talking is
 * cancelled and is NOT a dependency of this surface.
 *
 * No write is reachable from this surface: the Homi write seam is a
 * server-side authority with no client contract, so nothing here simulates a
 * mutation or offers a confirmation it cannot execute.
 */
export function HomiSurface() {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const auth = useAuth();
  const navigation = useNavigation<any>();
  const insets = useSafeAreaInsets();

  const accessToken = auth.session?.access_token ?? null;
  const actorId = auth.authMe?.person?.id ?? null;
  const householdId = auth.authMe?.active_household?.id ?? null;
  const householdName = auth.authMe?.active_household?.name ?? null;

  const [conversationId, setConversationId] = useState(generateConversationId);
  const conversationIdRef = useRef(conversationId);
  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);
  const [messages, setMessages] = useState<HomiMessage[]>([]);
  const [input, setInput] = useState('');
  const [turnState, dispatchTurn] = React.useReducer(homiTurnReducer as any, 'idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorRetryable, setErrorRetryable] = useState(false);
  const [pendingTurn, setPendingTurn] = useState<PendingTurn | null>(null);
  const [pendingProposal, setPendingProposal] = useState<{ conversationId: string; proposal: any } | null>(null);
  /** F01-B: one lifecycle action at a time; blocks confirm after cancel. */
  const [proposalBusy, setProposalBusy] = useState(false);
  const [selectedAttachment, setSelectedAttachment] = useState<SelectedAttachment>(null);
  const [uploadedAttachment, setUploadedAttachment] = useState<UploadedAttachment | null>(null);
  const [uploading, setUploading] = useState(false);
  const [homiAvailable, setHomiAvailable] = useState<boolean | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const missingContext = !accessToken || !actorId || !householdId || !HOMI_CONFIGURED;

  const handleConfirmProposal = async () => {
    if (!pendingProposal || !accessToken || !actorId || !householdId || proposalBusy) return;
    setProposalBusy(true);
    try {
      const result = await invokeHomi({
        text: '',
        accessToken,
        actorId,
        householdId,
        conversationId: pendingProposal.conversationId,
        proposalAction: 'confirm',
      });
      setMessages((prev) => [...prev, createHomiMessage({ role: 'assistant', text: result.answer, status: 'sent', created_at: nowIso(), turn_id: result.turnId })]);
      setPendingProposal(null);
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : 'Error al confirmar');
    } finally {
      setProposalBusy(false);
    }
  };

  const handleCancelProposal = async () => {
    if (!pendingProposal || !accessToken || !actorId || !householdId || proposalBusy) return;
    setProposalBusy(true);
    try {
      const result = await invokeHomi({
        text: '',
        accessToken,
        actorId,
        householdId,
        conversationId: pendingProposal.conversationId,
        proposalAction: 'cancel',
      });
      setMessages((prev) => [...prev, createHomiMessage({ role: 'assistant', text: result.answer, status: 'sent', created_at: nowIso(), turn_id: result.turnId })]);
      setPendingProposal(null);
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : 'Error al cancelar');
    } finally {
      setProposalBusy(false);
    }
  };

  // HOMI V1 — manual dictation transport
  const [voiceState, setVoiceState] = useState<HomiVoiceUiState>('idle');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceSupported, setVoiceSupported] = useState(false);
  /** True once the transport is known to be unusable on this runtime. */
  const [voiceUnavailable, setVoiceUnavailable] = useState(false);
  /** A transcript is in the composer as a draft; it is NOT a sent message. */
  const [voiceDraftReady, setVoiceDraftReady] = useState(false);
  /** Text written before dictation, restored if the draft is discarded. */
  const voiceDraftPreviousTextRef = useRef<string>('');
  const voiceTransportRef = useRef<HomiVoiceTransport | null>(null);
  const voiceRecordingRef = useRef(false);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      void voiceTransportRef.current?.release();
      voiceTransportRef.current = null;
    };
  }, []);

  const ensureVoiceTransport = useCallback(async (): Promise<HomiVoiceTransport | null> => {
    if (voiceTransportRef.current) return voiceTransportRef.current;
    if (!accessToken || !actorId || !householdId) return null;

    // HOMI V1: a single manual dictation transport. There is no runtime
    // switch, no continuous listening and no realtime/VAD path.
    const transport = await createHomiVoiceTransport({ accessToken });
    await transport.initialize();
    voiceTransportRef.current = transport;
    setVoiceSupported(true);
    setVoiceUnavailable(false);
    return transport;
  }, [accessToken, actorId, householdId]);

  // The voice channel must announce itself before the user asks for it: the
  // control only renders when a transport exists, so the availability probe
  // cannot be the press itself. When the runtime cannot host the transport the
  // surface says so and the textual channel stays open.
  useEffect(() => {
    if (missingContext || !HOMI_CONFIGURED) return;
    let cancelled = false;
    void (async () => {
      try {
        await ensureVoiceTransport();
      } catch (error) {
        if (cancelled) return;
        // Keep the microphone retryable: a failed availability probe only
        // means this client build cannot host expo-audio *right now*. The user
        // can fix that by opening the bundle with an Expo Go SDK 58 client (or
        // a development build that includes expo-audio) and tapping again.
        // Hiding the control here used to disable voice for the whole session.
        setVoiceSupported(true);
        setVoiceUnavailable(false);
        setVoiceError(
          error instanceof Error
            ? error.message
            : 'No se pudo inicializar el audio de voz.',
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [missingContext, ensureVoiceTransport]);

  const runHealthCheck = useCallback(async () => {
    setHomiAvailable(null);
    const ok = await homiHealthCheck();
    setHomiAvailable(ok);
  }, []);

  // Health check on mount
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const ok = await homiHealthCheck();
      if (!cancelled) setHomiAvailable(ok);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const clearAttachment = useCallback(() => {
    setSelectedAttachment(null);
    setUploadedAttachment(null);
    setErrorMessage(null);
  }, []);

  const pickImageAttachment = useCallback(async () => {
    try {
      const ImagePicker = await import('expo-image-picker');
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setErrorMessage('Homi necesita permiso para acceder a tus fotos.');
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 1,
      });
      if (result.canceled || !result.assets?.length) return;
      const asset = result.assets[0];
      const name = asset.fileName ?? `imagen.${asset.mimeType?.includes('png') ? 'png' : 'jpg'}`;
      const uri = await stageAttachmentUri(asset.uri, name);
      const inferred = inferMimeFromName(name);
      const pickerMime = asset.mimeType && asset.mimeType !== 'application/octet-stream'
        ? asset.mimeType
        : undefined;
      const type = pickerMime ?? inferred ?? 'image/jpeg';
      setSelectedAttachment({
        uri,
        name,
        type,
        size: asset.fileSize,
        declaredMime: pickerMime ? undefined : inferred ?? undefined,
      });
      setErrorMessage(null);
    } catch (err: any) {
      setErrorMessage(err.message || 'No se pudo abrir la galería.');
    }
  }, []);

  const pickDocumentAttachment = useCallback(async () => {
    try {
      const result = await (await import('expo-document-picker')).getDocumentAsync({
        type: [
          'application/pdf',
          'text/*',
          'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        ],
        copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets?.length) return;
      const asset = result.assets[0];
      const name = asset.name ?? 'archivo';
      const inferred = inferMimeFromName(name);
      const pickerMime = asset.mimeType && asset.mimeType !== 'application/octet-stream'
        ? asset.mimeType
        : undefined;
      const type = pickerMime ?? inferred ?? 'application/octet-stream';
      setSelectedAttachment({
        uri: asset.uri,
        name,
        type,
        size: asset.size,
        declaredMime: pickerMime ? undefined : inferred ?? undefined,
      });
      setErrorMessage(null);
    } catch (err: any) {
      setErrorMessage(err.message || 'No se pudo seleccionar el documento.');
    }
  }, []);

  const handlePickFile = useCallback(() => {
    if (missingContext) {
      setErrorMessage('Sesión o hogar no disponibles.');
      return;
    }
    if (!HOMI_CONFIGURED) {
      setErrorMessage('HOMI no está configurado en esta compilación.');
      return;
    }
    Alert.alert('Adjuntar a Homi', 'Elegí qué querés enviar.', [
      { text: 'Foto o imagen', onPress: () => void pickImageAttachment() },
      { text: 'Documento (PDF)', onPress: () => void pickDocumentAttachment() },
      { text: 'Cancelar', style: 'cancel' },
    ]);
  }, [missingContext, pickImageAttachment, pickDocumentAttachment]);

  const handleRemoveAttachment = useCallback(async () => {
    if (uploadedAttachment && householdId && actorId && accessToken) {
      try {
        await deleteAttachment({
          attachmentId: uploadedAttachment.attachment_id,
          householdId,
          actorId,
          accessToken,
        });
      } catch {
        // Ignore delete errors - user can still send without attachment
      }
    }
    clearAttachment();
  }, [uploadedAttachment, householdId, actorId, accessToken, clearAttachment]);

  const deliverTurn = useCallback(
    async (turn: PendingTurn) => {
      const text = turn.text.trim();
      const attachment = turn.attachment;

      const userMessage = createHomiMessage({
        role: 'user',
        text: text || '[Adjunto]',
        status: 'pending',
        kind: attachment ? 'attachment' : 'text',
        attachment: attachment
          ? {
              attachment_id: attachment.attachment_id,
              original_filename: attachment.original_filename,
              mime_type: attachment.mime_type,
              size_bytes: attachment.size_bytes,
            }
          : undefined,
        created_at: nowIso(),
        turn_id: generateTurnId(),
      });

      setMessages((prev) => [...prev, userMessage]);
      setInput('');
      // The draft became a message: clear the editable-draft hint.
      setVoiceDraftReady(false);
      voiceDraftPreviousTextRef.current = '';
      setErrorMessage(null);
      setErrorRetryable(false);
      dispatchTurn({ type: 'SUBMIT', text });

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const result = await invokeHomi({
          text,
          accessToken: accessToken!,
          actorId: actorId!,
          householdId: householdId!,
          conversationId,
          signal: controller.signal,
          attachments: attachment ? [{ attachment_id: attachment.attachment_id }] : undefined,
          turnId: userMessage.turn_id,
        });

        setMessages((prev) =>
          prev.map((m) => (m.id === userMessage.id ? { ...m, status: 'sent' } : m)),
        );

        const assistantMessage = createHomiMessage({
          role: 'assistant',
          text: result.answer,
          status: 'sent',
          kind: result.seeResults && result.seeResults.length > 0 ? 'see_result' : 'text',
          see_result: result.seeResults && result.seeResults.length > 0 ? result.seeResults[0] : undefined,
          created_at: nowIso(),
          turn_id: result.turnId,
        });

        setMessages((prev) => [...prev, assistantMessage]);
        if (result.decisionKind === 'action_proposal') {
          setPendingProposal({ conversationId, proposal: result.proposal });
        } else {
          setPendingProposal(null);
        }
        setPendingTurn(null);
        dispatchTurn({ type: 'RESOLVED' });
      } catch (error) {
        if (error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')) {
          // F01-A: the HTTP request was stopped. No late response can be
          // incorporated (the awaited call rejected). Mark the user turn as
          // cancelled and free the loading state; do NOT claim any backend
          // write was reverted.
          setMessages((prev) =>
            prev.map((m) => (m.id === userMessage.id ? { ...m, status: 'cancelled' } : m)),
          );
          if (attachment) {
            try {
              await deleteAttachment({
                attachmentId: attachment.attachment_id,
                householdId: householdId!,
                actorId: actorId!,
                accessToken: accessToken!,
              });
            } catch {
              // Best-effort cleanup of a cancelled turn's upload.
            }
          }
          setPendingTurn(null);
          dispatchTurn({ type: 'ABORT' });
          return;
        }
        setMessages((prev) =>
          prev.map((m) => (m.id === userMessage.id ? { ...m, status: 'failed' } : m)),
        );
        const retryable = !(error instanceof ApiError && error.status === 0);
        setErrorMessage(
          error instanceof ApiError ? error.message : 'No pudimos conectar con Homi.',
        );
        setErrorRetryable(retryable);
        if (!retryable && attachment) {
          try {
            await deleteAttachment({
              attachmentId: attachment.attachment_id,
              householdId: householdId!,
              actorId: actorId!,
              accessToken: accessToken!,
            });
          } catch {
            // Best-effort cleanup: do not hide the original turn error.
          }
        }
        setPendingTurn(retryable ? turn : null);
        dispatchTurn({ type: 'REJECTED' });
      } finally {
        abortRef.current = null;
      }
    },
    [accessToken, actorId, householdId, conversationId],
  );

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text && !uploadedAttachment) return;
    if (turnState === 'sending') return;
    if (missingContext) {
      setErrorMessage('Sesión o hogar no disponibles.');
      dispatchTurn({ type: 'REJECTED' });
      return;
    }
    if (uploading) {
      setErrorMessage('Esperando a que termine la subida del adjunto...');
      return;
    }

    let finalUploadedAttachment = uploadedAttachment;
    if (selectedAttachment && !uploadedAttachment) {
      setUploading(true);
      setErrorMessage(null);
      try {
        const result = await uploadAttachment({
          file: {
            uri: selectedAttachment.uri,
            name: selectedAttachment.name,
            type: selectedAttachment.type,
          },
          householdId: householdId!,
          actorId: actorId!,
          accessToken: accessToken!,
          conversationId,
          declaredMime: selectedAttachment.declaredMime,
        });
        finalUploadedAttachment = {
          attachment_id: result.attachment_id,
          original_filename: result.original_filename,
          mime_type: result.mime_type,
          size_bytes: result.size_bytes,
        };
        setUploadedAttachment(finalUploadedAttachment);
      } catch (err: any) {
        setUploading(false);
        if (err instanceof AbortError || (err instanceof Error && err.name === 'AbortError')) {
          return;
        }
        setErrorMessage(err.message || 'No se pudo subir el adjunto.');
        return;
      } finally {
        setUploading(false);
      }
    }

    setUploadedAttachment(null);
    setSelectedAttachment(null);
    await deliverTurn({ text, attachment: finalUploadedAttachment });
  }, [
    input,
    uploadedAttachment,
    selectedAttachment,
    uploading,
    turnState,
    missingContext,
    accessToken,
    actorId,
    householdId,
    conversationId,
    deliverTurn,
  ]);

  const handleRetry = useCallback(() => {
    const turn = pendingTurn;
    if (!turn) return;
    setErrorMessage(null);
    setErrorRetryable(false);
    void deliverTurn(turn);
  }, [pendingTurn, deliverTurn]);

  const handleDismissError = useCallback(() => {
    setErrorMessage(null);
    setPendingTurn(null);
    dispatchTurn({ type: 'DISMISS_ERROR' });
  }, []);

  // --- DEMO V1 Planner READ: real read tool, real TaskCards ----------------
  const runPlannerRead = useCallback(async () => {
    if (missingContext) {
      setErrorMessage('Sesión o hogar no disponibles.');
      return;
    }
    setErrorMessage(null);
    setErrorRetryable(false);

    const requestId = generateTurnId();
    setMessages((prev) => [
      ...prev,
      createHomiMessage({
        role: 'system',
        text: 'Leyendo tus tareas…',
        status: 'pending',
        kind: 'text',
        created_at: nowIso(),
        turn_id: requestId,
      }),
    ]);
    dispatchTurn({ type: 'SUBMIT', text: 'planner.read' });

    try {
      const tasks = await readPlannerTasks({
        actorId: actorId!,
        householdId: householdId!,
        accessToken: accessToken!,
      });

      const toolResult: HomiToolResult = {
        tool_id: 'planner.tasks.list',
        result: { tasks },
      };

      setMessages((prev) => [
        ...prev.filter((message) => message.turn_id !== requestId),
        createHomiMessage({
          role: 'system',
          text:
            tasks.length > 0
              ? `Leí ${tasks.length === 1 ? '1 tarea' : `${tasks.length} tareas`} de tu Planner.`
              : 'No hay tareas para mostrar en tu Planner.',
          status: 'sent',
          kind: 'tool_result',
          tool_result: toolResult,
          created_at: nowIso(),
          turn_id: requestId,
        }),
      ]);
      dispatchTurn({ type: 'RESOLVED' });
    } catch (error) {
      setMessages((prev) => prev.filter((message) => message.turn_id !== requestId));
      setErrorMessage(
        error instanceof ApiError ? error.message : 'No pudimos leer tus tareas.',
      );
      setErrorRetryable(!(error instanceof ApiError && error.status === 0));
      dispatchTurn({ type: 'REJECTED' });
    }
  }, [missingContext, actorId, householdId, accessToken]);

  const handleSuggestion = useCallback(
    (suggestion: HomiSuggestion) => {
      if (suggestion.kind === 'planner_read') {
        void runPlannerRead();
        return;
      }
      setInput(suggestion.label);
    },
    [runPlannerRead],
  );

  const handleNewConversation = useCallback(() => {
    abortRef.current?.abort();
    const transport = voiceTransportRef.current;
    voiceTransportRef.current = null;
    setVoiceSupported(false);
    setVoiceState('idle');
    setVoiceError(null);
    setVoiceDraftReady(false);
    voiceDraftPreviousTextRef.current = '';
    voiceRecordingRef.current = false;
    void transport?.release();
    setMessages([]);
    setInput('');
    setErrorMessage(null);
    setPendingTurn(null);
    setConversationId(generateConversationId());
    dispatchTurn({ type: 'CANCEL' });
  }, []);

  // HOMI V1 — manual dictation. A transcript only becomes an editable draft
  // in the composer: it is NEVER a sent message and never runs tools.
  const handleVoicePress = useCallback(async () => {
    setVoiceError(null);

    try {
      const transport = await ensureVoiceTransport();
      if (!transport) {
        setVoiceError('Sesión o hogar no disponibles.');
        setVoiceState('error');
        return;
      }

      if (voiceRecordingRef.current) {
        // Second tap: stop the native recorder and transcribe the audio. No
        // THINK, no tools, no TTS and no automatic message creation here.
        voiceRecordingRef.current = false;
        setVoiceState('uploading');
        const capture = await transport.stopCapture();
        const result = await transport.deliverTurn(capture);

        // Preserve text written before dictation. The transcript is appended
        // as a draft; it never silently overwrites the composer.
        const existing = voiceDraftPreviousTextRef.current ?? '';
        const separator = existing.trim() && !/\s$/.test(existing) ? ' ' : '';
        setInput(
          existing.trim() ? `${existing}${separator}${result.transcript}` : result.transcript,
        );
        setVoiceDraftReady(true);
        setVoiceState('idle');
        return;
      }

      // First tap: start recording. There is no VAD or automatic endpointing.
      voiceDraftPreviousTextRef.current = input;
      await transport.startCapture();
      voiceRecordingRef.current = true;
      setVoiceDraftReady(false);
      setVoiceState('recording');
    } catch (error) {
      voiceRecordingRef.current = false;
      setVoiceState('error');
      const message =
        error instanceof HomiVoiceError
          ? error.message
          : error instanceof Error
            ? error.message
            : 'No se pudo completar el dictado.';
      setVoiceError(message);
      // Recover in place: a failed STT must never require leaving HOMI, and
      // the text already written in the composer stays untouched.
      const current = voiceTransportRef.current;
      if (current?.recover) {
        void current.recover().catch(() => undefined);
      }
    }
  }, [ensureVoiceTransport, input]);

  const handleVoiceCancel = useCallback(async () => {
    const transport = voiceTransportRef.current;
    voiceRecordingRef.current = false;
    setVoiceError(null);
    setVoiceState('idle');
    setVoiceDraftReady(false);
    voiceDraftPreviousTextRef.current = '';
    if (!transport) return;
    try {
      await transport.cancelCapture();
    } catch {
      // Nothing to cancel: the microphone is already released.
    }
  }, []);

  /** Discard only the transcribed draft; restore the pre-dictation text. */
  const handleDiscardVoiceDraft = useCallback(() => {
    setInput(voiceDraftPreviousTextRef.current ?? '');
    voiceDraftPreviousTextRef.current = '';
    setVoiceDraftReady(false);
    setVoiceError(null);
    setVoiceState('idle');
  }, []);

  // --- Boot, unavailable and configuration states -------------------------
  if (homiAvailable === null) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator color={theme.colors.terracotta[600]} />
        <AppText variant="bodySmall" tone="secondary">
          Verificando conexión con Homi…
        </AppText>
      </View>
    );
  }

  if (homiAvailable === false) {
    return (
      <View style={styles.container}>
        <HomiHeader householdName={householdName} onClose={() => navigation.goBack()} />
        <View style={[styles.centered, styles.stateBody]}>
          <ErrorState
            title="No pudimos conectar con Homi"
            description="El servicio no responde en este momento. Podés reintentar ahora o más tarde."
            retryLabel="Reintentar"
            onRetry={() => void runHealthCheck()}
          />
        </View>
      </View>
    );
  }

  if (missingContext) {
    return (
      <View style={styles.container}>
        <HomiHeader householdName={householdName} onClose={() => navigation.goBack()} />
        <View style={[styles.centered, styles.stateBody]}>
          <ErrorState
            title="Configuración incompleta"
            description={
              HOMI_CONFIGURED
                ? 'Sesión o hogar no disponibles. Elegí un hogar activo y volvé a entrar.'
                : 'HOMI no está configurado en esta compilación.'
            }
          />
        </View>
      </View>
    );
  }

  const thinking = turnState === 'sending';

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <HomiHeader
        householdName={householdName}
        onClose={() => navigation.goBack()}
        onNewConversation={handleNewConversation}
      />

      {pendingProposal ? (
        <View style={{ padding: 12, borderWidth: 1, borderColor: '#ccc', margin: 8, borderRadius: 8 }}>
          <AppText>Propuesta: {JSON.stringify(pendingProposal.proposal)}</AppText>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
            <HomiPressable onPress={handleConfirmProposal} disabled={proposalBusy} accessibilityLabel="Confirmar la propuesta"><AppText>Confirmar</AppText></HomiPressable>
            <HomiPressable onPress={handleCancelProposal} disabled={proposalBusy} accessibilityLabel="Cancelar la propuesta"><AppText>Cancelar</AppText></HomiPressable>
          </View>
        </View>
      ) : null}

      <HomiMessageList
        messages={messages}
        isThinking={thinking}
        errorMessage={errorMessage}
        errorRetryable={errorRetryable}
        onRetry={handleRetry}
        onDismissError={handleDismissError}
        emptyState={
          <HomiEmptyState suggestions={HOMI_DEMO_SUGGESTIONS} onSuggestion={handleSuggestion} />
        }
      />

      <View style={{ paddingBottom: Math.max(insets.bottom, theme.spacing[2]) }}>
        <HomiComposer
          value={input}
          onChangeText={setInput}
          onSend={() => void handleSend()}
          onCancelRequest={() => abortRef.current?.abort()}
          disabled={missingContext}
          sending={turnState === 'sending'}
          onAttachFile={handlePickFile}
          attachment={selectedAttachment}
          onRemoveAttachment={() => void handleRemoveAttachment()}
          uploading={uploading}
          voiceState={voiceState}
          voiceSupported={voiceSupported}
          voiceUnavailable={voiceUnavailable}
          voiceError={voiceError}
          voiceDraft={voiceDraftReady}
          onVoiceDraftDiscard={handleDiscardVoiceDraft}
          onVoicePress={() => void handleVoicePress()}
          onVoiceCancel={() => void handleVoiceCancel()}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function HomiHeader({
  householdName,
  onClose,
  onNewConversation,
}: {
  householdName: string | null;
  onClose: () => void;
  onNewConversation?: () => void;
}) {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);

  return (
    <View style={styles.header}>
      <HomiPressable
        onPress={onClose}
        accessibilityLabel="Cerrar Homi"
        style={styles.headerButton}
      >
        <HomePlusIcon name="close" size={20} color={theme.colors.text.secondary} />
      </HomiPressable>

      <View style={styles.headerIdentity}>
        <View style={styles.headerBadge}>
          <HomePlusIcon name="sparkles" size={18} color={theme.colors.terracotta[600]} />
        </View>
        <View style={styles.headerTitles}>
          <AppText variant="title3" weight="700">
            Homi
          </AppText>
          {householdName ? (
            <AppText variant="caption" tone="tertiary" numberOfLines={1}>
              {householdName}
            </AppText>
          ) : null}
        </View>
      </View>

      {onNewConversation ? (
        <HomiPressable
          onPress={onNewConversation}
          accessibilityLabel="Empezar una conversación nueva"
          style={styles.headerButton}
        >
          <HomePlusIcon name="create-outline" size={20} color={theme.colors.text.secondary} />
        </HomiPressable>
      ) : (
        <View style={styles.headerButton} />
      )}
    </View>
  );
}

const makeStyles = (theme: ReturnType<typeof useHomiTheme>) =>
  StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: theme.colors.background.base,
    },
    centered: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: homiSpacing.intraTurn,
      padding: theme.spacing[5],
    },
    stateBody: {
      paddingHorizontal: theme.spacing[5],
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.intraTurn,
      minHeight: 56,
      paddingHorizontal: theme.spacing[2],
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    headerButton: {
      width: theme.touchTargets.normal,
      height: theme.touchTargets.normal,
      borderRadius: theme.radius.full,
      alignItems: 'center',
      justifyContent: 'center',
    },
    headerIdentity: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.intraTurn,
    },
    headerBadge: {
      width: 36,
      height: 36,
      borderRadius: theme.radius.full,
      backgroundColor: theme.colors.terracotta[50],
      alignItems: 'center',
      justifyContent: 'center',
    },
    headerTitles: {
      flex: 1,
    },
  });
