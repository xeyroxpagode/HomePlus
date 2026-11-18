import type { AuthMe } from './api';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/**
 * Runtime boundary for the authenticated account projection.
 * TypeScript cannot protect the app from a malformed or missing HTTP payload.
 */
export function parseAuthMeProjection(value: unknown): AuthMe {
  if (!isRecord(value)) {
    throw new TypeError('Auth projection must be an object.');
  }

  if (!Array.isArray(value.memberships)) {
    throw new TypeError('Auth projection memberships must be an array.');
  }

  if (!isRecord(value.navigation) || typeof value.navigation.next !== 'string') {
    throw new TypeError('Auth projection navigation is missing or invalid.');
  }

  if (value.person !== null && !isRecord(value.person)) {
    throw new TypeError('Auth projection person must be an object or null.');
  }

  if (value.active_household !== null && !isRecord(value.active_household)) {
    throw new TypeError('Auth projection active household must be an object or null.');
  }

  return value as AuthMe;
}
