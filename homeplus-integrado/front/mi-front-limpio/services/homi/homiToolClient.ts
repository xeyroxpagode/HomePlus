import { requestJson, OPERATION_KINDS } from '../api';
import type { HomiTaskDto } from './homiMessages';

/**
 * Cliente de tool READ de Planner para la superficie HOMI V1.
 * AdaptaciÃ³n 18/11: ya no llama al gateway antiguo con claims del cliente.
 * Usa el tool canÃ³nico `planner.tasks.list` del gateway versionado; la
 * identidad y el hogar se derivan server-side del bearer.
 */
export const readPlannerTasks = async (input: {
  accessToken: string;
  actorId?: string;
  householdId?: string;
}): Promise<HomiTaskDto[]> => {
  const response = await requestJson<{ data?: { tasks?: HomiTaskDto[] } | HomiTaskDto[] }>(
    '/api/homi/v1/tools/planner.tasks.list/invoke',
    {
      method: 'POST',
      accessToken: input.accessToken,
      body: {},
      operationKind: OPERATION_KINDS.READ_ONLY,
    },
  );
  const data = response?.data;
  if (Array.isArray(data)) return data;
  if (data && Array.isArray((data as { tasks?: HomiTaskDto[] }).tasks)) {
    return (data as { tasks: HomiTaskDto[] }).tasks;
  }
  return [];
};

