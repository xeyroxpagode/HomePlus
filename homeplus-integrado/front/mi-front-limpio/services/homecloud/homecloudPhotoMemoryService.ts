import * as ImagePicker from 'expo-image-picker';
import { copyArtifactToDurableWorkspace } from './homecloudDurableArtifact';

import { getSharedUploadJobStore } from '../../storage/homecloudUploadJobStorage';
import type { HomeCloudCapabilityDescriptor } from './homecloudCapabilitiesAdapter';
import { fetchHomeCloudAlbumsCached } from './homecloudReadService';
import { createExpoFileSystemUploadTransport, createFetchArtifactReader, createUploadEngine } from './homecloudUploadEngine';
import { recoverUploadJobs } from './homecloudUploadRecovery';
import type { UploadJob, UploadLocalArtifact } from './homecloudUploadTypes';
import { homeCloudUploadErrorMessage } from './homecloudUploadError';
import { memoryDevTrace } from './homecloudMemoryDiagnostics';

export const PHOTO_MEMORY_INTAKE_SOURCE = 'homecloud:photo';

export type PhotoMemoryStatus =
  | 'idle'
  | 'preview'
  | 'picking'
  | 'uploading'
  | 'completed'
  | 'failed';

export interface PhotoMemoryState {
  status: PhotoMemoryStatus;
  error?: string;
  contentId?: string;
  artifact?: UploadLocalArtifact;
}

export interface PhotoMemoryAlbum {
  id: string | null;
  name: string;
}

export interface PhotoMemoryConfig {
  householdId: string;
  accessToken: string;
  getAccessToken?: () => string | null;
  capabilities: HomeCloudCapabilityDescriptor;
  initialAlbumId?: string | null;
  intakeSource?: string;
}

export type PhotoPickResult =
  | { cancelled: true }
  | { cancelled: false; artifact: UploadLocalArtifact };

const IMAGE_MIME_BY_EXTENSION: Readonly<Record<string, string>> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  heic: 'image/heic',
  heif: 'image/heif',
};

function safeExtension(fileName: string | null | undefined, uri: string): string | null {
  const source = fileName || uri.split('?')[0] || '';
  const match = source.toLowerCase().match(/\.([a-z0-9]{2,5})$/);
  return match?.[1] ?? null;
}

function safeDisplayName(fileName: string | null | undefined, extension: string | null): string {
  const cleaned = fileName?.trim().replace(/[\\/:*?"<>|]/g, '-') ?? '';
  if (cleaned) return cleaned.slice(0, 180);
  return `Foto-${new Date().toISOString().replace(/[:.]/g, '-')}.${extension || 'jpg'}`;
}

/** Photo-only picker: no video, EXIF extraction, editor or base64 payload. */
export async function pickPhotoFromGallery(source: 'gallery' | 'camera' = 'gallery'): Promise<PhotoPickResult> {
  if (source === 'camera') {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) throw new Error('Permití el acceso a la cámara para sacar una foto.');
  }
  const launch = source === 'camera' ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync;
  const result = await launch({
    mediaTypes: ['images'],
    allowsMultipleSelection: false,
    allowsEditing: false,
    quality: 0.82,
    exif: false,
    base64: false,
  });
  if (result.canceled || !result.assets[0]) return { cancelled: true };

  const asset = result.assets[0];
  const extension = safeExtension(asset.fileName, asset.uri);
  const mimeType = (asset.mimeType || (extension ? IMAGE_MIME_BY_EXTENSION[extension] : null) || '').toLowerCase();
  if (!Object.values(IMAGE_MIME_BY_EXTENSION).includes(mimeType)) {
    throw new Error('Seleccioná una foto válida.');
  }

  let sizeBytes = asset.fileSize ?? 0;
  if (!sizeBytes) {
    // Synchronous require is Metro-resolved; Windows async import paths may contain a broken ./n/node_modules prefix.
    const FileSystem: typeof import('expo-file-system/legacy') = require('expo-file-system/legacy');
    const info = await FileSystem.getInfoAsync(asset.uri);
    sizeBytes = info.exists && 'size' in info && typeof info.size === 'number' ? info.size : 0;
  }
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    throw new Error('No pudimos leer la foto seleccionada.');
  }

  if (sizeBytes > 50 * 1024 * 1024) throw new Error('La foto supera el máximo de 50 MB. Elegí una más pequeña.');

  return {
    cancelled: false,
    artifact: {
      localUri: asset.uri,
      displayName: safeDisplayName(asset.fileName, extension),
      mimeType,
      sizeBytes,
      extension,
    },
  };
}

export function createPhotoMemoryUploadService(config: PhotoMemoryConfig) {
  const intakeSource = config.intakeSource ?? PHOTO_MEMORY_INTAKE_SOURCE;
  const getAccessToken = config.getAccessToken ?? (() => config.accessToken);
  const store = getSharedUploadJobStore();
  const engine = createUploadEngine({
    store,
    readArtifact: createFetchArtifactReader(),
    uploadTransport: createExpoFileSystemUploadTransport(),
    getAccessToken,
    getHouseholdId: () => config.householdId,
  });

  let selectedAlbumId = config.initialAlbumId ?? null;
  let currentJob: UploadJob | null = null;
  let selectedArtifact: UploadLocalArtifact | null = null;
  let state: PhotoMemoryState = { status: 'idle' };
  const listeners = new Set<(next: PhotoMemoryState) => void>();

  const emit = (next: PhotoMemoryState) => {
    state = next;
    listeners.forEach((listener) => listener(state));
  };

  const runJob = async (job: UploadJob): Promise<string | null> => {
    currentJob = job;
    emit({ status: 'uploading' });
    try {
      const completed = await engine.run(job.id);
      currentJob = completed;
      const contentId = completed.contentId ?? null;
      emit({ status: 'completed', contentId: contentId ?? undefined });
      return contentId;
    } catch (error) {
      currentJob = store.get(job.id) ?? job;
      memoryDevTrace('photo_upload_failed', {
        state: currentJob.state,
        kind: error instanceof Error ? error.name : 'unknown',
        moduleResolutionFailure: error instanceof Error && error.message.includes('Unable to resolve module'),
      });
      emit({
        status: 'failed',
        artifact: selectedArtifact ?? undefined,
        error: homeCloudUploadErrorMessage(error, 'No pudimos guardar la foto. Revisá tu conexión y reintentá.'),
      });
      return null;
    }
  };

  return {
    subscribe(listener: (next: PhotoMemoryState) => void): () => void {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    async loadAlbums(): Promise<PhotoMemoryAlbum[]> {
      const token = getAccessToken();
      if (!token) return [{ id: null, name: 'Recuerdos' }];
      try {
        const albums = await fetchHomeCloudAlbumsCached(token, { householdId: config.householdId });
        return [{ id: null, name: 'Recuerdos' }, ...albums.map((album) => ({ id: album.id, name: album.name }))];
      } catch {
        return [{ id: null, name: 'Recuerdos' }];
      }
    },
    selectAlbum(albumId: string | null): void {
      selectedAlbumId = albumId;
    },
    async pick(source: 'gallery' | 'camera' = 'gallery'): Promise<void> {
      if (!config.capabilities.contribute) {
        emit({ status: 'failed', error: 'No tenés permiso para agregar recuerdos.' });
        return;
      }
      if (state.status === 'picking' || state.status === 'uploading') return;
      emit({ status: 'picking' });
      try {
        const picked = await pickPhotoFromGallery(source);
        if (picked.cancelled) {
          emit({ status: 'idle' });
          return;
        }
        currentJob = null;
        selectedArtifact = picked.artifact;
        emit({ status: 'preview', artifact: selectedArtifact });
      } catch (error) {
        emit({
          status: 'failed',
          error: error instanceof Error ? error.message : 'No pudimos abrir tu galería.',
        });
        return;
      }
    },
    async uploadSelected(): Promise<string | null> {
      if (!selectedArtifact || state.status === 'uploading' || !config.capabilities.contribute) return null;
      emit({ status: 'uploading', artifact: selectedArtifact });
      try {
        const durable = await copyArtifactToDurableWorkspace(selectedArtifact);
        const job = engine.createJob({ role: 'memory', intakeSource, initialAlbumId: selectedAlbumId, capturePrecision: 'unknown' }, durable);
        return runJob(job);
      } catch (error) {
        emit({ status: 'failed', artifact: selectedArtifact, error: homeCloudUploadErrorMessage(error, 'No pudimos preparar la foto.') });
        return null;
      }
    },
    discardSelection(): void {
      if (state.status === 'uploading' || state.status === 'picking') return;
      selectedArtifact = null;
      currentJob = null;
      emit({ status: 'idle' });
    },
    async retry(): Promise<string | null> {
      if (state.status === 'uploading') return null;
      if (!currentJob && selectedArtifact) return this.uploadSelected();
      if (!currentJob) {
        await store.hydrate();
        const candidates = store
          .all()
          .filter((job) => job.householdId === config.householdId && job.intakeSource === intakeSource && job.state === 'failed')
          .sort((a, b) => a.updatedAt.localeCompare(b.updatedAt));
        currentJob = candidates[candidates.length - 1] ?? null;
      }
      return currentJob ? runJob(currentJob) : null;
    },
    async recover(): Promise<void> {
      await recoverUploadJobs({
        store,
        householdId: config.householdId,
        role: 'memory',
        intakeSource,
        run: (jobId) => engine.run(jobId),
        onJob: (job) => {
          currentJob = job;
          if (job.state === 'completed') emit({ status: 'completed', contentId: job.contentId ?? undefined });
        },
      });
      const failed = store.all().filter(job => job.householdId === config.householdId && job.intakeSource === intakeSource && job.state === 'failed').at(-1);
      if (failed && state.status === 'idle') {
        currentJob = failed;
        emit({ status: 'failed', error: 'Una foto quedó pendiente. Podés reintentar la carga.' });
      }
    },
    reset(): void {
      emit({ status: 'idle' });
    },
  };
}
