import React, { useEffect } from 'react';

import { useAuth } from './AuthContext';
import { useHousehold } from './HouseholdContext';
import { useAppRefresh } from './AppRefreshContext';
import { plannerCache } from '../services/planner/plannerCache';
import { supabase } from '../supabase';

/**
 * Shared Planner task signal for every private surface.  Cards only consume
 * plannerChangedAt; they never create their own Postgres subscriptions.
 */
export function PlannerTaskRealtimeBridge({ children }: { children: React.ReactNode }) {
  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  const { markPlannerChanged } = useAppRefresh();
  const accessToken = session?.access_token ?? null;
  const householdId = currentHousehold?.id ?? null;

  useEffect(() => {
    if (!accessToken || !householdId) return undefined;
    let active = true;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    void supabase.realtime.setAuth(accessToken).then(() => {
      if (!active) return;
      channel = supabase
        .channel(`planner-tasks:${householdId}`)
        .on('postgres_changes', {
          event: '*', schema: 'public', table: 'planner_tasks', filter: `household_id=eq.${householdId}`,
        }, (payload) => {
          const row = (payload.new && Object.keys(payload.new).length ? payload.new : payload.old) as { id?: string } | null;
          if (!row?.id) return;
          plannerCache.executeInvalidation(
            { kind: 'task', action: payload.eventType === 'DELETE' ? 'trash' : 'update', entityId: row.id },
            { householdId },
          );
          if (__DEV__) console.log('[Planner] realtime.task.changed', { householdId, taskId: row.id, event: payload.eventType });
          markPlannerChanged();
        })
        .subscribe();
    }).catch(() => undefined);

    return () => {
      active = false;
      if (channel) void supabase.removeChannel(channel);
    };
  }, [accessToken, householdId, markPlannerChanged]);

  return <>{children}</>;
}
