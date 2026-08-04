/**
 * Composition root.
 *
 * Three things happen here and nowhere else: the query client is created, the
 * router is mounted, and the boot state is wired to both.
 *
 * The wiring is the interesting part. The router's gate reads the boot model
 * through a module-level store rather than a hook (Q48 puts the guard in
 * `beforeLoad`, which runs outside React), so something has to tell the router
 * to re-evaluate when that model changes. That is `BootSync`.
 */

import { useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';

import { primeBackendInfo } from '@/core/api/client';
import { signalAppReady } from '@/core/boot/appReady';
import { useBootModel } from '@/core/boot/bootStore';
import { router } from '@/core/router/router';

// The locked TanStack Query defaults: this is a local backend and invalidation
// is event-driven, never time-driven. A refetch on window focus would fire on
// every alt-tab and buy nothing.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: Infinity,
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

export function AppRoot() {
  return (
    <QueryClientProvider client={queryClient}>
      <BootSync />
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

/**
 * Renders nothing. Keeps the router and the API credentials in step with the
 * boot machine.
 */
function BootSync() {
  const { snapshot, sessionEpoch } = useBootModel();

  useEffect(() => {
    // `useEffect` runs post-commit, so by the time this fires the webview has
    // something to show and revealing the window cannot flash white (Q54).
    signalAppReady();
  }, []);

  useEffect(() => {
    // The gate is a `beforeLoad`, so it only re-runs on navigation. Without
    // this the app would sit on the boot screen after the handshake completes,
    // waiting for a navigation that nothing is going to trigger.
    void router.invalidate();
  }, [snapshot.phase, snapshot.boot_id]);

  useEffect(() => {
    if (sessionEpoch === 0) return;

    // Q78: a new session means a new token *and* a cache belonging to a
    // process that no longer exists. Clear before anything can read it.
    queryClient.clear();
    void primeBackendInfo();
  }, [sessionEpoch]);

  return null;
}
