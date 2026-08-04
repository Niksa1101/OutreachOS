/**
 * The boot gate, as a pure function.
 *
 * Q48 puts the guard in the root route's `beforeLoad`. That runs during
 * navigation, so the decision it makes is worth testing on its own rather than
 * through the router — and the interesting cases (a retry landing while the
 * user is on `/diagnostics`, a workspace picked while the shell is mounted) are
 * awkward to drive through a real navigation.
 */

import type { BootPhase } from '@/core/boot/bootState';

export const SETUP_PATH = '/setup';
export const DIAGNOSTICS_PATH = '/diagnostics';
export const HOME_PATH = '/';

/** Routes that exist outside the shell layout and are not "somewhere to
 * return to" once the app is healthy. */
const GATE_PATHS: readonly string[] = [SETUP_PATH, DIAGNOSTICS_PATH];

export function isGatePath(pathname: string): boolean {
  return GATE_PATHS.includes(pathname);
}

/**
 * Where the router should be, given the boot phase and where it is now.
 *
 * `null` means "stay". Returning a target unconditionally would make every
 * navigation a redirect and defeat the router's own history handling.
 */
export function resolveGate(
  phase: BootPhase,
  pathname: string,
  rememberedPath: string,
): string | null {
  switch (phase) {
    case 'awaiting_workspace':
      return pathname === SETUP_PATH ? null : SETUP_PATH;

    case 'failed':
      return pathname === DIAGNOSTICS_PATH ? null : DIAGNOSTICS_PATH;

    case 'ready':
      // Q78: on a successful retry the user goes back where they were, not to
      // the home route — which is why the remembered path is tracked at all.
      if (isGatePath(pathname)) {
        return isGatePath(rememberedPath) ? HOME_PATH : rememberedPath;
      }
      return null;

    // The boot screen renders in place of the route tree during these, so
    // navigation is left alone. Redirecting here would rewrite the URL the
    // user came back to before the app knows whether it can honour it.
    case 'starting':
    case 'starting_backend':
      return null;
  }
}
