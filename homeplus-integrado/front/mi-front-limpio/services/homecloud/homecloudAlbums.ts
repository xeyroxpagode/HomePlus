import * as Crypto from 'expo-crypto';
import { requestJson, OPERATION_KINDS } from '../api';
import { plannerCache } from '../planner/plannerCache';
import type { HomeCloudAlbum } from './homecloudTypes';

export const albumIntentId = () => Crypto.randomUUID();
export type PhotoPreferences = { available: boolean; favoriteIds?: string[]; covers?: { albumId: string; contentId: string }[] };
export const readPhotoPreferences = (accessToken: string) => requestJson<PhotoPreferences>('/api/homecloud/memories/preferences', { accessToken, operationKind: OPERATION_KINDS.READ_ONLY });
export const setPhotoFavorite = (accessToken: string, contentId: string, favorite: boolean) => requestJson(`/api/homecloud/memories/${contentId}/favorite`, { accessToken, method: favorite ? 'PUT' : 'DELETE', operationKind: OPERATION_KINDS.NON_VERSIONED_MUTATION });
export const setAlbumCover = (accessToken: string, albumId: string, contentId: string) => requestJson(`/api/homecloud/albums/${albumId}/cover/${contentId}`, { accessToken, method: 'PUT', operationKind: OPERATION_KINDS.NON_VERSIONED_MUTATION });
export async function createMemoryAlbum(token: string, id: string, name: string): Promise<HomeCloudAlbum> {
  const result = await requestJson<{ album: HomeCloudAlbum }>('/api/homecloud/albums', { accessToken: token, method: 'POST', operationKind: OPERATION_KINDS.NON_VERSIONED_MUTATION, body: { id, name } });
  plannerCache.invalidatePrefix(['homecloud', 'albums']);
  return result.album;
}
export async function updateMemoryAlbum(token: string, id: string, name?: string) {
  await requestJson(`/api/homecloud/albums/${id}${name === undefined ? '/trash' : ''}`, { accessToken: token, method: name === undefined ? 'POST' : 'PATCH', operationKind: OPERATION_KINDS.NON_VERSIONED_MUTATION, body: name === undefined ? undefined : { name } });
  plannerCache.invalidatePrefix(['homecloud', 'albums']);
}
export async function setMemoryAlbumMembership(token: string, albumId: string, contentId: string, included: boolean) {
  await requestJson(`/api/homecloud/albums/${albumId}/items/${contentId}`, { accessToken: token, method: included ? 'PUT' : 'DELETE', operationKind: OPERATION_KINDS.NON_VERSIONED_MUTATION });
  plannerCache.invalidatePrefix(['homecloud', 'albums']);
}
