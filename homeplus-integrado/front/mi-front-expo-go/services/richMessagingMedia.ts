import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import * as FileSystem from 'expo-file-system/legacy';
import { cancelMessageAttachmentUpload, createClientMessageId, authorizeMessageAttachmentUpload, registerMessageAttachment, sendAttachmentMessage, verifyMessageAttachmentUpload, type Message, type MessagingAttachment } from './messages';

export type LocalMessageMedia = {
  uri: string; kind: 'image' | 'audio' | 'file'; mimeType: string; originalName: string; sizeBytes: number;
  width?: number | null; height?: number | null; durationMs?: number | null;
};

const MAX_BYTES = 50 * 1024 * 1024;
const safeName = (name: string) => name.replace(/[\\/\0]/g, '_').slice(0, 180) || 'archivo';
const extension = (mime: string) => ({ 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'audio/mp4': 'm4a', 'audio/m4a': 'm4a', 'audio/mpeg': 'mp3', 'audio/ogg': 'ogg', 'audio/wav': 'wav', 'application/pdf': 'pdf', 'text/plain': 'txt' }[mime] ?? 'bin');

async function sizeOf(uri: string, supplied?: number | null) {
  if (supplied && supplied > 0) return supplied;
  const info = await FileSystem.getInfoAsync(uri);
  return info.exists && typeof info.size === 'number' ? info.size : 0;
}
function assertSize(sizeBytes: number) {
  if (!sizeBytes || sizeBytes > MAX_BYTES) throw new Error('El archivo debe pesar menos de 50 MB.');
}

async function normalizeImage(asset: ImagePicker.ImagePickerAsset): Promise<LocalMessageMedia> {
  const sourceMime = asset.mimeType === 'image/png' ? 'image/png' : 'image/jpeg';
  // Strip EXIF and cap the longest side before any upload. The native module
  // performs this off the JS thread and returns an orientation-normalized file.
  const scale = Math.max(asset.width ?? 0, asset.height ?? 0);
  const result = await ImageManipulator.manipulateAsync(asset.uri, scale > 1920 ? [{ resize: asset.width && asset.width >= (asset.height ?? 0) ? { width: 1920 } : { height: 1920 } }] : [], { compress: 0.82, format: ImageManipulator.SaveFormat.JPEG });
  const sizeBytes = await sizeOf(result.uri);
  assertSize(sizeBytes);
  return { uri: result.uri, kind: 'image', mimeType: 'image/jpeg', originalName: safeName(asset.fileName ?? `foto.${extension(sourceMime)}`), sizeBytes, width: result.width, height: result.height };
}

export async function pickMessageImage(source: 'camera' | 'gallery'): Promise<LocalMessageMedia | null> {
  const permission = source === 'camera' ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) throw new Error(source === 'camera' ? 'Necesitás permitir la cámara para sacar una foto.' : 'Necesitás permitir la galería para elegir una foto.');
  const result = source === 'camera'
    ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 1, exif: false })
    : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: false, quality: 1, exif: false });
  if (result.canceled || !result.assets?.[0]) return null;
  return normalizeImage(result.assets[0]);
}

export async function pickMessageFile(): Promise<LocalMessageMedia | null> {
  const result = await DocumentPicker.getDocumentAsync({ multiple: false, copyToCacheDirectory: true, type: ['application/pdf', 'text/plain', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'] });
  if (result.canceled || !result.assets?.[0]) return null;
  const asset = result.assets[0]; const mimeType = asset.mimeType ?? 'application/octet-stream';
  const sizeBytes = await sizeOf(asset.uri, asset.size); assertSize(sizeBytes);
  return { uri: asset.uri, kind: 'file', mimeType, originalName: safeName(asset.name ?? `archivo.${extension(mimeType)}`), sizeBytes };
}

export async function uploadAndSendMessageMedia(input: { accessToken: string; conversationId: string; media: LocalMessageMedia; onProgress?: (value: number) => void; clientMessageId?: string; clientAttachmentId?: string }): Promise<Message> {
  const clientAttachmentId = input.clientAttachmentId ?? createClientMessageId();
  const clientMessageId = input.clientMessageId ?? createClientMessageId();
  input.onProgress?.(0.05);
  const registered = await registerMessageAttachment(input.accessToken, input.conversationId, {
    kind: input.media.kind, mime_type: input.media.mimeType, original_name: input.media.originalName, size_bytes: input.media.sizeBytes,
    client_attachment_id: clientAttachmentId, width: input.media.width ?? null, height: input.media.height ?? null, duration_ms: input.media.durationMs ?? null,
  });
  try {
    // An interrupted client may have completed its PUT. Verify first so retry
    // resumes at the correct phase instead of creating/re-uploading a copy.
    let uploaded = registered.attachment.lifecycle === 'uploaded' || registered.attachment.lifecycle === 'committed';
    if (!uploaded) {
      try { await verifyMessageAttachmentUpload(input.accessToken, registered.attachment.id); uploaded = true; } catch { /* object is not there yet */ }
    }
    if (!uploaded) {
      const authorization = await authorizeMessageAttachmentUpload(input.accessToken, registered.attachment.id);
      const response = await FileSystem.uploadAsync(authorization.signed_upload_url, input.media.uri, {
        httpMethod: 'PUT', uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
        headers: { 'content-type': input.media.mimeType, 'x-upsert': 'false' },
      });
      if (response.status < 200 || response.status >= 300) throw new Error('No pudimos subir el adjunto.');
      input.onProgress?.(0.85);
      await verifyMessageAttachmentUpload(input.accessToken, registered.attachment.id);
    }
    const sent = await sendAttachmentMessage(input.accessToken, input.conversationId, input.media.kind, registered.attachment.id, clientMessageId);
    input.onProgress?.(1);
    return sent.message;
  } catch (error) {
    // If the commit succeeded but its response was lost, the guarded server
    // cancel is a no-op. For every uncommitted state it removes the orphan.
    void cancelMessageAttachmentUpload(input.accessToken, registered.attachment.id).catch(() => {});
    throw error;
  }
}

export const formatAttachmentSize = (bytes: number) => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
export type { MessagingAttachment };
