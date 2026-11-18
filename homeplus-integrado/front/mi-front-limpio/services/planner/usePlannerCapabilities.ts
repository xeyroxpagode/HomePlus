import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';

import { ApiError } from '../api';
import {
  fetchPlannerCapabilities,
  hasCapability,
  type PlannerCapability,
  type PlannerCapabilitiesProjection,
} from '../plannerCapabilities';
import { plannerCache } from './plannerCache';
import { plannerKeys, type CapabilityScope } from './plannerKeys';

export type PlannerCapabilitiesScope = {
  accountId: string | null;
  householdId: string | null;
  membershipId: string | null;
};

type MembershipLike = {
  id: string;
  household_id: string;
  status: string;
};

export const resolvePlannerCapabilityScope = (input: {
  accountId: string | null;
  householdId: string | null;
  memberships: readonly MembershipLike[] | null | undefined;
}): PlannerCapabilitiesScope => {
  const membership = (input.memberships ?? []).find(
    (item) => item.household_id === input.householdId && item.status === 'active',
  );
  return {
    accountId: input.accountId,
    householdId: input.householdId,
    membershipId: membership?.id ?? null,
  };
};

export function usePlannerCapabilities(
  accessToken: string | null,
  scope: PlannerCapabilitiesScope,
): {
  capabilities: PlannerCapabilitiesProjection | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  can: (capability: PlannerCapability) => boolean;
} {
  const [capabilities, setCapabilities] = useState<PlannerCapabilitiesProjection | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);
  const { accountId, householdId, membershipId } = scope;
  const cacheScope: CapabilityScope | null = useMemo(
    () => (accountId && householdId && membershipId
      ? { accountId, householdId, membershipId }
      : null),
    [accountId, householdId, membershipId],
  );

  const runFetch = useCallback(async () => {
    if (!accessToken || !householdId) return;
    const sequence = ++requestSeq.current;
    setLoading(true);
    try {
      const projection = await fetchPlannerCapabilities(accessToken);
      if (sequence !== requestSeq.current) return;
      setCapabilities(projection);
      setError(null);
      if (cacheScope) plannerCache.set(plannerKeys.capabilities(cacheScope), projection);
    } catch (caught) {
      if (sequence !== requestSeq.current) return;
      setError(caught instanceof Error ? caught.message : 'No pudimos verificar tus permisos en Planner.');
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
        setCapabilities({} as PlannerCapabilitiesProjection);
        if (cacheScope) plannerCache.invalidate(plannerKeys.capabilities(cacheScope));
      }
    } finally {
      if (sequence === requestSeq.current) setLoading(false);
    }
  }, [accessToken, cacheScope, householdId]);

  useEffect(() => {
    requestSeq.current += 1;
    if (!accessToken || !householdId) {
      setCapabilities(null);
      setLoading(false);
      setError(null);
      return;
    }
    const cached = cacheScope
      ? plannerCache.get<PlannerCapabilitiesProjection>(plannerKeys.capabilities(cacheScope))
      : null;
    if (cached) setCapabilities(cached);
    else setCapabilities(null);
    void runFetch();
  }, [accessToken, cacheScope, householdId, runFetch]);

  useFocusEffect(useCallback(() => {
    void runFetch();
  }, [runFetch]));

  return {
    capabilities,
    loading,
    error,
    reload: () => void runFetch(),
    can: (capability) => capabilities ? hasCapability(capabilities, capability) : false,
  };
}
