import { requestJson } from '../api';
import {
  featureFlagStore,
  type HomePlusFeatureFlags,
} from './featureFlagStore';

export { featureFlagStore, isFeatureEnabled, type HomePlusFeatureFlags } from './featureFlagStore';

type ProjectionResponse = { flags?: Record<string, unknown> };

function normalizeProjection(input: Record<string, unknown> | undefined): HomePlusFeatureFlags {
  const flags: Record<string, boolean> = {};
  for (const [key, value] of Object.entries(input ?? {})) {
    if (typeof value === 'boolean') flags[key] = value;
  }
  return Object.freeze(flags);
}

export async function fetchFeatureFlagProjection(
  accessToken: string,
  accountId: string,
  householdId: string | null,
  signal?: AbortSignal,
): Promise<HomePlusFeatureFlags> {
  try {
    const response = await requestJson<ProjectionResponse>('/api/feature-flags', {
      accessToken,
      operationKind: 'READ_ONLY',
      signal,
      timeoutMs: 10_000,
    });
    const flags = normalizeProjection(response.flags);
    featureFlagStore.set(accountId, householdId, flags);
    return flags;
  } catch (error) {
    // The provider owns fallback and UI state. Keeping the original failure
    // lets it distinguish cancellation from a real offline/timeout failure.
    throw error;
  }
}
