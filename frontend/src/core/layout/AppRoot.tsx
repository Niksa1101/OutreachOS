/**
 * Composition root for the application shell.
 *
 * Checkpoint 2: the window is hidden until this paints, so the only real job
 * here is to signal readiness. The boot state machine arrives in checkpoint 3,
 * the workspace gate in checkpoint 4, and the sidebar shell in checkpoint 6.
 *
 * Design tokens do not exist until checkpoint 6 and hardcoded values are a
 * review failure per Tech.md §3.3. The inline values below are the pre-token
 * boot surface — the same exemption `BootErrorBoundary` takes, and deleted at
 * the same time.
 */

import { useEffect } from 'react';

import { signalAppReady } from '@/core/boot/appReady';

export function AppRoot() {
  useEffect(() => {
    // `useEffect` runs post-commit, so by the time this fires the webview has
    // something to show and revealing the window cannot flash white.
    signalAppReady();
  }, []);

  return (
    <main
      style={{
        display: 'grid',
        placeContent: 'center',
        minHeight: '100vh',
        gap: '0.5rem',
        textAlign: 'center',
        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
        color: '#fafafa',
        background: '#09090b',
      }}
    >
      <h1 style={{ fontSize: '1.125rem', fontWeight: 600, letterSpacing: '-0.01em', margin: 0 }}>
        OutreachOS
      </h1>
      <p style={{ margin: 0, fontSize: '0.875rem', opacity: 0.6 }}>Starting…</p>
    </main>
  );
}
