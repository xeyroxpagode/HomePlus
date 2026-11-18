import React, { useEffect, useState } from 'react';
import { Image, Linking, Modal, Pressable, StyleSheet, View } from 'react-native';
import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { AppText } from '../ui';
import { colors, radius, spacing } from '../../constants/theme';
import { getMessageAttachmentDownload, type Message, type MessagingAttachment } from '../../services/messages';
import { formatAttachmentSize } from '../../services/richMessagingMedia';
import { MessageContextCard } from './MessageContextCard';

function AttachmentUrl({ attachment, accessToken, children }: { attachment: MessagingAttachment; accessToken: string | null; children: (url: string | null) => React.ReactNode }) {
  const [url, setUrl] = useState<string | null>(attachment.local_uri ?? null);
  useEffect(() => { let live = true; if (!accessToken || attachment.local_uri) return undefined; void getMessageAttachmentDownload(accessToken, attachment.id).then((value) => { if (live) setUrl(value.signed_url); }).catch(() => { if (live) setUrl(null); }); return () => { live = false; }; }, [accessToken, attachment.id, attachment.local_uri]);
  return <>{children(url)}</>;
}
function AudioCard({ attachment, accessToken }: { attachment: MessagingAttachment; accessToken: string | null }) {
  return <AttachmentUrl attachment={attachment} accessToken={accessToken}>{(url) => url ? <AudioPlayer url={url} attachment={attachment} /> : <AppText tone="secondary">Cargando audio…</AppText>}</AttachmentUrl>;
}
function AudioPlayer({ url, attachment }: { url: string; attachment: MessagingAttachment }) {
  const player = useAudioPlayer(url, { updateInterval: 250 }); const status = useAudioPlayerStatus(player);
  const [speed, setSpeed] = useState(1);
  const duration = attachment.duration_ms ?? status.duration * 1000;
  const setNextSpeed = () => { const next = speed === 1 ? 1.5 : speed === 1.5 ? 2 : 1; setSpeed(next); player.playbackRate = next; };
  return <View style={styles.audio} testID="messages.media.audio"><Pressable testID="messages.audio.play" onPress={() => status.playing ? player.pause() : player.play()} accessibilityLabel={status.playing ? 'Pausar audio' : 'Reproducir audio'} style={styles.audioCircle}><AppText tone="inverse" weight="800">{status.playing ? 'Ⅱ' : '▶'}</AppText></Pressable><View style={{ flex: 1 }}><AppText variant="caption" weight="800">Audio · {Math.ceil(duration / 1000)} s</AppText><View style={styles.progress}><View style={[styles.progressFill, { width: `${Math.min(100, (status.currentTime * 1000 / Math.max(duration, 1)) * 100)}%` }]} /></View></View><Pressable testID="messages.audio.speed" onPress={setNextSpeed} accessibilityLabel={`Velocidad ${speed}x`}><AppText variant="caption" weight="800">{speed}×</AppText></Pressable></View>;
}
export function MessageRenderer({ message, mine, accessToken }: { message: Message; mine: boolean; accessToken: string | null }) {
  const attachment = message.attachments?.[0];
  const [viewer, setViewer] = useState(false);
  if (message.type === 'task' && message.context_entity_id) return <MessageContextCard type="task" entityId={message.context_entity_id} />;
  if (!attachment) return <View style={[styles.bubble, mine ? styles.mine : styles.theirs]}><AppText variant="bodySmall" tone={mine ? 'inverse' : 'primary'}>{message.delivery === 'sending' && message.type !== 'text' ? 'Preparando adjunto…' : message.body}</AppText></View>;
  if (attachment.kind === 'image') return <AttachmentUrl attachment={attachment} accessToken={accessToken}>{(url) => <><Pressable testID="messages.media.image" onPress={() => url && setViewer(true)} accessibilityLabel={`Abrir imagen ${attachment.original_name}`} style={styles.imageWrap}>{url ? <Image source={{ uri: url }} style={styles.image} resizeMode="cover" /> : <AppText tone="secondary">Cargando foto…</AppText>}{message.delivery === 'sending' ? <AppText variant="caption" tone="secondary">Subiendo {Math.round((attachment.upload_progress ?? 0) * 100)}%</AppText> : null}</Pressable><Modal visible={viewer} transparent onRequestClose={() => setViewer(false)}><View style={styles.viewer}><Pressable onPress={() => setViewer(false)} accessibilityLabel="Cerrar imagen" style={styles.close}><AppText tone="inverse" weight="800">Cerrar</AppText></Pressable>{url ? <Image source={{ uri: url }} style={styles.fullImage} resizeMode="contain" /> : null}</View></Modal></>}</AttachmentUrl>;
  if (attachment.kind === 'audio') return <AudioCard attachment={attachment} accessToken={accessToken} />;
  return <AttachmentUrl attachment={attachment} accessToken={accessToken}>{(url) => <Pressable testID="messages.media.file" onPress={() => url && void Linking.openURL(url)} accessibilityLabel={`Abrir archivo ${attachment.original_name}`} style={styles.file}><View style={styles.fileBadge}><AppText>▤</AppText></View><View style={{ flex: 1 }}><AppText variant="bodySmall" weight="800" numberOfLines={2}>{attachment.original_name}</AppText><AppText variant="caption" tone="secondary">{attachment.mime_type} · {formatAttachmentSize(attachment.size_bytes)}</AppText></View></Pressable>}</AttachmentUrl>;
}
const styles = StyleSheet.create({ bubble: { borderRadius: radius.xl, padding: spacing[3] }, mine: { backgroundColor: colors.terracotta[600] }, theirs: { backgroundColor: colors.surface.card, borderWidth: 1, borderColor: colors.border.subtle }, imageWrap: { width: 220, minHeight: 130, overflow: 'hidden', borderRadius: radius.lg, backgroundColor: colors.surface.soft, justifyContent: 'center', alignItems: 'center' }, image: { width: 220, height: 180 }, viewer: { flex: 1, backgroundColor: '#101010', justifyContent: 'center' }, fullImage: { width: '100%', height: '82%' }, close: { alignSelf: 'flex-end', margin: spacing[4], padding: spacing[2] }, audio: { minWidth: 224, minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: spacing[2], padding: spacing[2], borderRadius: radius.lg, backgroundColor: colors.surface.card, borderWidth: 1, borderColor: colors.border.subtle }, audioCircle: { width: 40, height: 40, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand }, progress: { height: 4, marginTop: 5, overflow: 'hidden', borderRadius: radius.pill, backgroundColor: colors.border.subtle }, progressFill: { height: 4, backgroundColor: colors.brand }, file: { minWidth: 230, maxWidth: 300, minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: spacing[2], padding: spacing[3], borderRadius: radius.lg, backgroundColor: colors.surface.card, borderWidth: 1, borderColor: colors.border.subtle }, fileBadge: { width: 36, height: 36, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.terracotta[50] } });
