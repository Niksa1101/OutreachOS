/**
 * Tell Rust the boot UI has painted, so it can show the window.
 *
 * Q54: the window is created with `"visible": false`. Without that, the user
 * sees a white flash before any boot state renders. Rust runs a 3s watchdog
 * against this call (Q77), so a frontend that never gets here still produces a
 * visible window — this is the fast path, not the only one.
 */

import { invoke } from '@tauri-apps/api/core';

let signalled = false;

/**
 * Idempotent and non-throwing.
 *
 * Called from two places that can both legitimately be first: the boot UI's
 * layout effect, and the error boundary's mount. Q77 wants a *caught* crash to
 * reveal the window immediately rather than after 3s of apparent hang, which
 * means the error boundary has to be allowed to race the happy path.
 */
export function signalAppReady(): void {
  if (signalled) return;
  signalled = true;

  invoke('app_ready').catch(() => {
    // Outside a Tauri webview (a plain `vite dev` in a browser) there is no
    // IPC bridge. The window is already visible in that case, so there is
    // nothing to recover.
  });
}

/** Test seam. */
export function __resetAppReadyForTests(): void {
  signalled = false;
}
