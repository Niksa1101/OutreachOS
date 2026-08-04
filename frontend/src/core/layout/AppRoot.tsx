/**
 * Composition root for the application shell.
 *
 * Checkpoint 3: the boot state machine drives what renders, and a ready
 * backend brings up the SSE stream. The workspace gate and the real
 * diagnostics screen arrive in checkpoint 4; the router and sidebar shell in
 * checkpoint 6.
 *
 * Design tokens do not exist until checkpoint 6 and hardcoded values are a
 * review failure per Tech.md §3.3. The inline values below are the pre-token
 * boot surface — the same exemption `BootErrorBoundary` takes, and deleted at
 * the same time.
 */

import { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { primeBackendInfo } from '@/core/api/client';
import { signalAppReady } from '@/core/boot/appReady';
import { useBootState } from '@/core/boot/useBootState';
import { EventStreamProvider } from '@/core/sse/EventStreamProvider';
import { useStreamStatus } from '@/core/sse/streamStatus';

// TanStack Query defaults, per the locked assumptions: this is a local backend
// and invalidation is event-driven, never time-driven. A refetch on window
// focus would fire on every alt-tab and buy nothing.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: Infinity,
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

const shell: React.CSSProperties = {
  display: 'grid',
  placeContent: 'center',
  minHeight: '100vh',
  gap: '0.75rem',
  textAlign: 'center',
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
  color: '#fafafa',
  background: '#09090b',
  padding: '2rem',
};

const mono: React.CSSProperties = {
  fontFamily: 'ui-monospace, monospace',
  fontSize: '0.8125rem',
  opacity: 0.7,
};

export function AppRoot() {
  return (
    <QueryClientProvider client={queryClient}>
      <BootGate />
    </QueryClientProvider>
  );
}

function BootGate() {
  const { snapshot, sessionEpoch } = useBootState();
  const [credentialsReady, setCredentialsReady] = useState(false);

  useEffect(() => {
    // `useEffect` runs post-commit, so by the time this fires the webview has
    // something to show and revealing the window cannot flash white.
    signalAppReady();
  }, []);

  useEffect(() => {
    if (sessionEpoch === 0) return;

    setCredentialsReady(false);
    // Q78: a new session means a new token *and* a cache from a process that
    // no longer exists. Clear before anything can read it.
    queryClient.clear();

    let cancelled = false;
    void primeBackendInfo().then(() => {
      if (!cancelled) setCredentialsReady(true);
    });

    return () => {
      cancelled = true;
    };
  }, [sessionEpoch]);

  if (snapshot.phase === 'failed' && snapshot.diagnostic) {
    // Checkpoint 4 replaces this with the real diagnostics screen — nine
    // codes, log tails, and the action set each code implies.
    return (
      <main style={shell}>
        <h1 style={{ fontSize: '1rem', margin: 0 }}>OutreachOS cannot start</h1>
        <p style={{ margin: 0, opacity: 0.75 }}>{snapshot.diagnostic.message}</p>
        <p style={mono}>{snapshot.diagnostic.code}</p>
        {snapshot.diagnostic.detail ? (
          <pre style={{ ...mono, textAlign: 'left', whiteSpace: 'pre-wrap', maxWidth: '60ch' }}>
            {snapshot.diagnostic.detail}
          </pre>
        ) : null}
      </main>
    );
  }

  if (snapshot.phase !== 'ready' || !credentialsReady) {
    // Q102: wordmark and one status line. No spinner — checkpoint 6 adds the
    // 400ms delay before one appears, which needs the motion tokens.
    return (
      <main style={shell}>
        <h1 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>OutreachOS</h1>
        <p style={{ margin: 0, fontSize: '0.875rem', opacity: 0.6 }}>{snapshot.status}</p>
      </main>
    );
  }

  return (
    <EventStreamProvider sessionEpoch={sessionEpoch}>
      <Heartbeat port={snapshot.port} bootId={snapshot.boot_id} />
    </EventStreamProvider>
  );
}

/**
 * The P0 exit criterion made visible: a heartbeat received over SSE from the
 * sidecar. PRD §7 asks for exactly this and nothing more — no fake data, no
 * placeholder charts.
 */
function Heartbeat({ port, bootId }: { port: number | null; bootId: string }) {
  const { connected, lastHeartbeatAt, lastMessage } = useStreamStatus();

  return (
    <main style={shell}>
      <h1 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>OutreachOS</h1>
      <p style={{ margin: 0, fontSize: '0.875rem', opacity: 0.6 }}>
        {connected ? 'Connected to the backend.' : 'Reconnecting…'}
      </p>
      <dl
        style={{
          ...mono,
          display: 'grid',
          gridTemplateColumns: 'auto auto',
          gap: '0.25rem 1.5rem',
          margin: '1rem 0 0',
          textAlign: 'left',
        }}
      >
        <dt>port</dt>
        <dd style={{ margin: 0 }}>{port ?? '—'}</dd>
        <dt>boot_id</dt>
        <dd style={{ margin: 0 }}>{bootId.slice(0, 8)}</dd>
        <dt>heartbeat</dt>
        <dd style={{ margin: 0 }}>
          {lastHeartbeatAt ? lastHeartbeatAt.toLocaleTimeString() : 'waiting…'}
        </dd>
      </dl>
      {lastMessage ? <p style={mono}>{lastMessage}</p> : null}
    </main>
  );
}
