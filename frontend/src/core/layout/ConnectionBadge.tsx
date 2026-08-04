/**
 * The SSE connection indicator.
 *
 * This is the P0 exit criterion made permanently visible: PRD §7 asks for a
 * heartbeat received over SSE from the sidecar, and after checkpoint 6 the
 * home screen is an honest empty state rather than a status readout. The
 * heartbeat has to live somewhere, and the shell chrome is where a connection
 * indicator belongs anyway.
 */

import { useStreamStatus } from '@/core/sse/streamStatus';

export function ConnectionBadge() {
  const { connected, lastHeartbeatAt } = useStreamStatus();

  const title = lastHeartbeatAt
    ? `Last heartbeat at ${lastHeartbeatAt.toLocaleTimeString()}`
    : 'Waiting for the first heartbeat';

  return (
    <span
      className="flex items-center gap-2 font-mono text-xs text-muted-foreground"
      title={title}
      // The colour alone would carry the state, which fails for anyone who
      // cannot distinguish the two. The text does the work; the dot decorates.
      aria-live="polite"
    >
      <span
        aria-hidden
        className="size-1.5 rounded-full transition-colors"
        style={{
          backgroundColor: connected ? 'var(--color-success)' : 'var(--color-warning)',
          transitionDuration: 'var(--motion-base)',
        }}
      />
      {connected ? 'Connected' : 'Reconnecting…'}
    </span>
  );
}
