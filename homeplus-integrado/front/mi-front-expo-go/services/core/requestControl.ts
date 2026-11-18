import { appRequestRegistry } from './serverState';
import type { RequestAbortReason } from './requestFailure';

export type RequestControlOptions = {
  signal?: AbortSignal | null;
  timeoutMs?: number;
  scopeId?: string | null;
};

export function createRequestControl(options: RequestControlOptions = {}) {
  const controller = new AbortController();
  let abortReason: RequestAbortReason = 'unknown';
  const abort = (reason: RequestAbortReason) => {
    if (controller.signal.aborted) return;
    abortReason = reason;
    controller.abort();
  };
  const abortFromExternal = () => {
    const signalReason = options.signal?.reason;
    abort(typeof signalReason === 'string' ? signalReason as RequestAbortReason : 'external');
  };
  const unregister = appRequestRegistry.register(
    controller,
    options.scopeId ?? null,
    () => abort('lifecycle.cancel_all'),
  );
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;

  if (options.signal?.aborted) abort('external');
  else options.signal?.addEventListener('abort', abortFromExternal, { once: true });

  if (options.timeoutMs != null && options.timeoutMs > 0) {
    timeoutHandle = setTimeout(() => abort('timeout'), options.timeoutMs);
  }

  let disposed = false;
  return {
    signal: controller.signal,
    getAbortReason() {
      return abortReason;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      if (timeoutHandle) clearTimeout(timeoutHandle);
      options.signal?.removeEventListener('abort', abortFromExternal);
      unregister();
    },
  } as const;
}
