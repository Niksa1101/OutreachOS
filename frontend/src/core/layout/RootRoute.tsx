/**
 * What the root route renders once the gate has had its say.
 *
 * Lives here rather than in `router.tsx` so that file exports only the router
 * and its helpers. A module that exports both a component and a non-component
 * breaks React Fast Refresh — every edit to the route tree would remount the
 * whole application instead of hot-swapping.
 */

import { Outlet } from '@tanstack/react-router';

import { useBootModel } from '@/core/boot/bootStore';
import { BootScreen } from '@/core/layout/BootScreen';

export function RootRoute() {
  // The hook, not `getBootModel()`. The guard reads the store imperatively
  // because `beforeLoad` runs outside React; this is a component and has to
  // re-render when the phase changes.
  const { snapshot } = useBootModel();

  // The boot screen replaces the route tree rather than being a route of its
  // own. Q102 makes it a wordmark and one status line — there is nothing to
  // navigate to or from, and giving it a URL would let the user land on it.
  if (snapshot.phase === 'starting' || snapshot.phase === 'starting_backend') {
    return <BootScreen status={snapshot.status} />;
  }

  return <Outlet />;
}
