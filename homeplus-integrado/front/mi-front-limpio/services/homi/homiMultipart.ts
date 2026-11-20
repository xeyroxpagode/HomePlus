export type MultipartFailureCode =
  | 'aborted'
  | 'timeout'
  | 'network_error';

export type MultipartTextResponse = {
  status: number;
  ok: boolean;
  text: string;
};

export class MultipartTransportError extends Error {
  readonly code: MultipartFailureCode;

  constructor(code: MultipartFailureCode) {
    super(`multipart request failed: ${code}`);
    this.name = 'MultipartTransportError';
    this.code = code;
  }
}

/**
 * React Native must generate the multipart Content-Type and its boundary.
 * Remove a caller-provided Content-Type even if a future caller adds one by
 * mistake: a boundary-less multipart body is invalid at the gateway.
 */
export const buildMultipartHeaders = (
  headers: Record<string, string> = {},
): Record<string, string> =>
  Object.fromEntries(
    Object.entries(headers).filter(
      ([name]) => name.trim().toLowerCase() !== 'content-type',
    ),
  );

/**
 * Send a React Native FormData through the native XMLHttpRequest transport.
 *
 * Expo 58's winter fetch rejects `{uri, name, type}` FormData parts. React
 * Native's XMLHttpRequest accepts those parts and lets the native networking
 * module create the multipart boundary, so the file URI, filename and MIME
 * type remain intact.
 */
export const postMultipartText = ({
  url,
  body,
  headers = {},
  signal,
  timeoutMs,
}: {
  url: string;
  body: FormData;
  headers?: Record<string, string>;
  signal?: AbortSignal | null;
  timeoutMs: number;
}): Promise<MultipartTextResponse> =>
  new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new MultipartTransportError('aborted'));
      return;
    }

    const xhr = new XMLHttpRequest();
    let settled = false;

    const handleAbort = () => {
      xhr.abort();
    };

    const cleanup = () => {
      signal?.removeEventListener('abort', handleAbort);
    };

    const settle = (callback: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      callback();
    };

    xhr.open('POST', url, true);
    xhr.timeout = timeoutMs;

    for (const [name, value] of Object.entries(buildMultipartHeaders(headers))) {
      xhr.setRequestHeader(name, value);
    }

    xhr.onload = () => {
      settle(() => {
        const status = xhr.status;
        resolve({
          status,
          ok: status >= 200 && status < 300,
          text: xhr.responseText ?? '',
        });
      });
    };

    xhr.onerror = () => {
      settle(() => reject(new MultipartTransportError('network_error')));
    };

    xhr.ontimeout = () => {
      settle(() => reject(new MultipartTransportError('timeout')));
    };

    xhr.onabort = () => {
      settle(() => reject(new MultipartTransportError('aborted')));
    };

    signal?.addEventListener('abort', handleAbort, { once: true });

    try {
      xhr.send(body);
    } catch {
      settle(() => reject(new MultipartTransportError('network_error')));
    }
  });
