import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  featureFlagStore,
  fetchFeatureFlagProjection,
  isFeatureEnabled,
  type HomePlusFeatureFlags,
} from '../services/core/featureFlags';
import { isRequestCancelled } from '../services/core/requestFailure';
import { useAuth } from './AuthContext';
import { useHousehold } from './HouseholdContext';

type FeatureFlagsContextValue = {
  flags: HomePlusFeatureFlags;
  loading: boolean;
  status: 'loading' | 'ready' | 'fallback' | 'cancelled';
  reload: () => Promise<void>;
  isEnabled: (key: string) => boolean;
};

const EMPTY_FLAGS: HomePlusFeatureFlags = Object.freeze({});
const FeatureFlagsContext = createContext<FeatureFlagsContextValue | undefined>(undefined);

export function FeatureFlagsProvider({ children }: { children: React.ReactNode }) {
  const { session, user } = useAuth();
  const { currentHousehold } = useHousehold();
  const [flags, setFlags] = useState<HomePlusFeatureFlags>(EMPTY_FLAGS);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<FeatureFlagsContextValue['status']>('ready');
  const loadGeneration = useRef(0);
  const inflightRequest = useRef<{
    key: string;
    controller: AbortController;
    promise: Promise<void>;
  } | null>(null);

  const accountId = user?.id ?? null;
  const householdId = currentHousehold?.id ?? null;

  const reload = useCallback(async () => {
    const accessToken = session?.access_token;
    if (!accessToken || !accountId) {
      inflightRequest.current?.controller.abort('feature_flags.session_cleared');
      inflightRequest.current = null;
      setFlags(EMPTY_FLAGS);
      setLoading(false);
      setStatus('ready');
      return;
    }

    const requestKey = `${accountId}:${householdId ?? 'no-household'}`;
    if (inflightRequest.current?.key === requestKey) {
      return inflightRequest.current.promise;
    }

    // A new authenticated scope supersedes the old projection. This is the
    // only local replacement cancellation and it is explicitly classified.
    inflightRequest.current?.controller.abort('feature_flags.replaced');
    const generation = ++loadGeneration.current;
    const controller = new AbortController();
    setFlags(featureFlagStore.get(accountId, householdId));
    setLoading(true);
    setStatus('loading');

    const promise = (async () => {
      try {
        const projection = await fetchFeatureFlagProjection(accessToken, accountId, householdId, controller.signal);
        if (generation === loadGeneration.current) {
          setFlags(projection);
          setStatus('ready');
        }
      } catch (error) {
        if (generation !== loadGeneration.current) return;
        if (isRequestCancelled(error)) {
          setStatus('cancelled');
          return;
        }

        // Flags are optional capability gates: retain deny-safe defaults on a
        // real network/timeout failure and keep the rest of the app usable.
        featureFlagStore.set(accountId, householdId, EMPTY_FLAGS);
        setFlags(EMPTY_FLAGS);
        setStatus('fallback');
      } finally {
        if (inflightRequest.current?.controller === controller) inflightRequest.current = null;
        if (generation === loadGeneration.current) setLoading(false);
      }
    })();

    inflightRequest.current = { key: requestKey, controller, promise };
    return promise;
  }, [accountId, householdId, session?.access_token]);

  useEffect(() => {
    setFlags(EMPTY_FLAGS);
    void reload();
    return () => {
      if (__DEV__) console.log('[API QA] component.unmount', { component: 'FeatureFlagsProvider' });
      loadGeneration.current += 1;
      inflightRequest.current?.controller.abort('feature_flags.provider_unmount');
      inflightRequest.current = null;
    };
  }, [reload]);

  const value = useMemo<FeatureFlagsContextValue>(() => ({
    flags,
    loading,
    status,
    reload,
    isEnabled: (key) => isFeatureEnabled(flags, key),
  }), [flags, loading, reload, status]);

  return <FeatureFlagsContext.Provider value={value}>{children}</FeatureFlagsContext.Provider>;
}

export function useFeatureFlags() {
  const value = useContext(FeatureFlagsContext);
  if (!value) throw new Error('useFeatureFlags debe usarse dentro de FeatureFlagsProvider.');
  return value;
}
