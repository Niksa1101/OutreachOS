/**
 * The P0 exit criterion, made visible.
 *
 * PRD §7 asks for a running shell that proves every layer can talk to every
 * other layer: Tauri → Python sidecar → SQLite, with SSE flowing back to React.
 * This screen is the SSE half of that, and nothing more. No fake data, no
 * placeholder charts — checkpoint 6 replaces it with the module shell and its
 * honest empty states.
 */

import { useBootModel } from '@/core/boot/bootStore';
import { bootSurface, mono } from '@/core/layout/bootStyles';
import { useStreamStatus } from '@/core/sse/streamStatus';

export function HomeScreen() {
  const { snapshot } = useBootModel();
  const { connected, lastHeartbeatAt, lastMessage } = useStreamStatus();

  return (
    <main style={bootSurface}>
      <h1 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>OutreachOS</h1>
      <p style={{ margin: 0, fontSize: '0.875rem', opacity: 0.6 }}>
        {connected ? 'Connected to the backend.' : 'Reconnecting…'}
      </p>

      <dl
        style={{
          ...mono,
          display: 'grid',
          gridTemplateColumns: 'max-content max-content',
          gap: '0.25rem 1.5rem',
          margin: '1rem 0 0',
          textAlign: 'left',
          opacity: 0.75,
        }}
      >
        <dt>port</dt>
        <dd style={{ margin: 0 }}>{snapshot.port ?? '—'}</dd>
        <dt>boot_id</dt>
        <dd style={{ margin: 0 }}>{snapshot.boot_id.slice(0, 8) || '—'}</dd>
        <dt>heartbeat</dt>
        <dd style={{ margin: 0 }}>
          {lastHeartbeatAt ? lastHeartbeatAt.toLocaleTimeString() : 'waiting…'}
        </dd>
      </dl>

      {lastMessage ? <p style={{ ...mono, opacity: 0.6 }}>{lastMessage}</p> : null}
    </main>
  );
}
