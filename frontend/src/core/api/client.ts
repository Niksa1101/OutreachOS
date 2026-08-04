/**
 * The typed fetch wrapper, and the only place the shared secret lives.
 *
 * Q56: the token is a **module-scoped binding that is never exported**. The
 * fetch wrapper and the SSE client both live in this module tree and close over
 * it. The alternative — putting it in a Zustand store — makes it reachable from
 * any component and therefore eventually logged by someone's debug
 * `console.log`.
 *
 * Q96 fixes the policy:
 *
 * - 15s default timeout via `AbortController`, overridable per call.
 * - **No automatic retry.** This is a local backend; a request that failed
 *   failed for a reason, and a silent retry hides it.
 * - A 401 refetches backend info once, then retries that request exactly once.
 *   Exactly once, because a token that is still wrong the second time is a bug
 *   rather than a race, and looping on it would hammer a backend that is
 *   already unhappy.
 *
 * One note on how the timeout override should be used: P1 renders must be job
 * submission plus SSE progress, not a long-held HTTP request. An override
 * appearing on a render call is a signal that the async job path was skipped,
 * not that 15s was too short.
 */

import { invoke } from '@tauri-apps/api/core';

export const DEFAULT_TIMEOUT_MS = 15_000;

/** Mirrors `BackendInfo` in `src-tauri/src/boot.rs`. */
interface BackendInfo {
  port: number;
  token: string;
  boot_id: string;
}

/** Never exported. See the module docstring. */
let backend: BackendInfo | null = null;

/** Deduplicates concurrent refreshes so a burst of 401s makes one invoke. */
let refreshing: Promise<BackendInfo | null> | null = null;

/** Mirrors the envelope in `core/errors.py`. */
export interface ApiErrorBody {
  code:
    | 'validation_error'
    | 'not_found'
    | 'conflict'
    | 'workspace_error'
    | 'unauthorized'
    | 'internal_error';
  message: string;
  details?: Record<string, unknown> | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorBody['code'];
  readonly details: Record<string, unknown> | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? null;
  }
}

/** A transport failure: the request never produced a response. */
export class ApiTransportError extends Error {
  constructor(
    message: string,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = 'ApiTransportError';
  }
}

async function refreshBackendInfo(): Promise<BackendInfo | null> {
  refreshing ??= invoke<BackendInfo | null>('get_backend_info')
    .then((info) => {
      backend = info;
      return info;
    })
    .catch(() => null)
    .finally(() => {
      refreshing = null;
    });

  return refreshing;
}

/**
 * Called by the boot reducer when the phase reaches `ready`, and again on every
 * `boot_id` change. Q56: re-fetched on `boot_id` change, because Retry mints a
 * new token and the old one is dead the moment it does.
 */
export async function primeBackendInfo(): Promise<void> {
  await refreshBackendInfo();
}

/** Test seam and shutdown hook. */
export function forgetBackendInfo(): void {
  backend = null;
}

export interface RequestOptions extends Omit<RequestInit, 'signal'> {
  /**
   * Q96: explicit in the signature rather than implied, so adding one later
   * does not need a wrapper rewrite.
   */
  timeoutMs?: number;
  /** SSE is exempt from the timeout entirely — see `core/sse`. */
  signal?: AbortSignal;
}

function baseUrl(info: BackendInfo): string {
  // Tech.md §4.2: loopback only, on the port the sidecar reported.
  return `http://127.0.0.1:${info.port}/api/v1`;
}

async function send(info: BackendInfo, path: string, options: RequestOptions): Promise<Response> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  // A caller-supplied signal composes with the timeout rather than replacing
  // it: whichever fires first wins.
  options.signal?.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    return await fetch(`${baseUrl(info)}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...options.headers,
        Authorization: `Bearer ${info.token}`,
      },
    });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Issue one authenticated request.
 *
 * `path` is relative to `/api/v1` and must **not** carry a trailing slash —
 * Q95 disables redirects server-side, so one produces a 404 rather than a
 * redirect the CORS preflight would refuse to follow anyway.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let info = backend ?? (await refreshBackendInfo());
  if (!info) {
    throw new ApiTransportError('The backend is not running.');
  }

  let response: Response;
  try {
    response = await send(info, path, options);
  } catch (cause) {
    // Q78: a transport failure is *not* evidence the sidecar died. Rust's
    // child-exit event is the only thing that decides that, so this throws and
    // never navigates.
    throw new ApiTransportError(`Request to ${path} failed.`, cause);
  }

  if (response.status === 401) {
    const refreshed = await refreshBackendInfo();
    if (refreshed && refreshed.token !== info.token) {
      info = refreshed;
      try {
        response = await send(info, path, options);
      } catch (cause) {
        throw new ApiTransportError(`Request to ${path} failed after re-auth.`, cause);
      }
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorBody(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

async function readErrorBody(response: Response): Promise<ApiErrorBody> {
  try {
    const body = (await response.json()) as { error?: ApiErrorBody };
    if (body.error?.code) {
      return body.error;
    }
  } catch {
    // Fall through: a non-JSON error body is itself the information.
  }

  return {
    code: 'internal_error',
    message: `The backend returned ${response.status} with no error envelope.`,
  };
}

/**
 * Internal accessor for the SSE client, which needs the same credentials but
 * cannot use `apiFetch` — it holds a connection open rather than awaiting a
 * body. Not exported from `core/api/index.ts`.
 */
export function currentBackend(): BackendInfo | null {
  return backend;
}
