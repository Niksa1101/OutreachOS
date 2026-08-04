/**
 * Frontend error capture for the pre-ready phase.
 *
 * Q23 established the capture points; Q64 added the sink split and the loop
 * guard. Errors thrown during boot have no backend to POST to, so they go
 * through `invoke("log_client_error")` into `boot.log`.
 *
 * The loop guard is not paranoia. A failure *inside* the reporter — a
 * serialisation error, a rejected invoke — would itself be an unhandled
 * rejection, which re-enters the reporter, which fails again. One broken
 * response becomes an unbounded storm, and the log it is writing into is the
 * one a user was about to send us.
 */

import { invoke } from '@tauri-apps/api/core';

/** Mirrors `ClientError` in `src-tauri/src/commands.rs`. */
export interface ClientErrorReport {
  message: string;
  source: 'window.onerror' | 'unhandledrejection' | 'error-boundary';
  stack?: string | undefined;
  route?: string | undefined;
}

/** True while a report is in flight. See the loop guard note above. */
let reporting = false;

/** Reports dropped because the reporter was already running. */
let suppressed = 0;

let installed = false;

/**
 * Send one error to the Rust boot log.
 *
 * Never throws and never rejects — every caller is an error path, and an error
 * path that can itself fail is the loop this guard exists to break.
 */
export async function reportClientError(report: ClientErrorReport): Promise<void> {
  if (reporting) {
    suppressed += 1;
    return;
  }

  reporting = true;
  try {
    await invoke('log_client_error', { error: report });

    if (suppressed > 0) {
      const dropped = suppressed;
      suppressed = 0;
      // Report the count, not the errors. Replaying them would re-enter the
      // guard for each one and defeat it.
      await invoke('log_client_error', {
        error: {
          message: `${dropped} further client error(s) suppressed while reporting`,
          source: report.source,
        } satisfies ClientErrorReport,
      });
    }
  } catch {
    // The IPC bridge is gone, which means the window is going away too.
    // There is no third sink to escalate to.
  } finally {
    reporting = false;
  }
}

function describe(reason: unknown): { message: string; stack?: string | undefined } {
  if (reason instanceof Error) {
    return { message: `${reason.name}: ${reason.message}`, stack: reason.stack };
  }
  if (typeof reason === 'string') {
    return { message: reason };
  }
  try {
    return { message: JSON.stringify(reason) ?? String(reason) };
  } catch {
    return { message: String(reason) };
  }
}

/**
 * Install the global capture points. Idempotent — React 19 StrictMode mounts
 * effects twice in development and a second listener would double every report.
 */
export function installClientErrorReporting(): void {
  if (installed) return;
  installed = true;

  window.addEventListener('error', (event: ErrorEvent) => {
    const { message, stack } = describe(event.error ?? event.message);
    void reportClientError({
      message,
      source: 'window.onerror',
      stack,
      route: window.location.hash || window.location.pathname,
    });
  });

  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    const { message, stack } = describe(event.reason);
    void reportClientError({
      message,
      source: 'unhandledrejection',
      stack,
      route: window.location.hash || window.location.pathname,
    });
  });
}

/** Test seam. Resets the guard so a suppressed-count assertion starts clean. */
export function __resetClientErrorReportingForTests(): void {
  reporting = false;
  suppressed = 0;
  installed = false;
}
