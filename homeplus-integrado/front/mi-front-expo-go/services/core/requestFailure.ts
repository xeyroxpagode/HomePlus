export type RequestAbortReason =
  | 'external'
  | 'timeout'
  | 'lifecycle.cancel_all'
  | 'unknown'
  | `feature_flags.${string}`;
export type RequestFailureKind = 'cancelled' | 'timeout' | 'offline' | 'network';

const nativeCancellationPattern = /FetchRequestCanceledException|Fetch request has been canceled|\bAbortError\b|\baborted\b/i;
const offlinePattern = /network request failed|failed to fetch|network is unreachable|offline/i;

export function classifyTransportFailure(
  error: unknown,
  options: { signalAborted: boolean; abortReason: RequestAbortReason },
): RequestFailureKind {
  if (options.abortReason === 'timeout') return 'timeout';
  if (options.signalAborted) return 'cancelled';

  const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error ?? '');
  // React Native iOS reports a native cancellation as
  // FetchRequestCanceledException rather than DOM AbortError during refresh.
  if (nativeCancellationPattern.test(message)) return 'cancelled';
  if (offlinePattern.test(message)) return 'offline';
  return 'network';
}

export function isRequestCancelled(error: unknown): boolean {
  return error instanceof Error
    && error.name === 'AbortError'
    && (error as Error & { kind?: RequestFailureKind }).kind === 'cancelled';
}
