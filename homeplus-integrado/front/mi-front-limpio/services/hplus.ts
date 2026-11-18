import { requestJson } from './api';

export type HPlusLedgerEntry = {
  id: string;
  membership_id: string;
  event_type: 'task_completed';
  source_type: 'planner_task';
  source_id: string;
  points: 5 | 10 | 20;
  occurred_at: string;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type HPlusSummary = {
  my_points: number;
  household_points: number;
  recent_entries: HPlusLedgerEntry[];
};

export const getHPlusSummary = (accessToken: string) =>
  requestJson<HPlusSummary>('/api/hplus/summary', { accessToken });

export const getHPlusLedger = (accessToken: string, limit = 30) =>
  requestJson<{ entries: HPlusLedgerEntry[] }>(`/api/hplus/ledger?limit=${limit}`, { accessToken });
