/**
 * The application shell.
 *
 * Q104: this mounts **only** in the ready phase. The gate routes a degraded
 * backend to `/diagnostics` before it gets here, which is what lets every
 * screen inside assume a working database rather than each handling 503.
 *
 * Q66: the single SSE connection is owned here, inside the ready state,
 * because before that there is no port and no token to connect with.
 *
 * Checkpoint 6 replaces the bare `<Outlet/>` with the shadcn sidebar and the
 * module registry's nav entries.
 */

import { Outlet } from '@tanstack/react-router';

import { useBootModel } from '@/core/boot/bootStore';
import { EventStreamProvider } from '@/core/sse/EventStreamProvider';

export function ShellLayout() {
  const { sessionEpoch } = useBootModel();

  return (
    <EventStreamProvider sessionEpoch={sessionEpoch}>
      <Outlet />
    </EventStreamProvider>
  );
}
