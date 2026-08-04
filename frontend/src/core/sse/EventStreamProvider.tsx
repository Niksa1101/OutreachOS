/**
 * Owns the single SSE connection.
 *
 * Q66: one provider, mounted inside the ready-state shell, dispatching into
 * TanStack Query. Mounted *inside* the ready state and not above it, because
 * before that there is no port and no token to connect with.
 *
 * The connection is keyed on `sessionEpoch`, so a Retry that mints a new
 * `boot_id` tears the old stream down and builds a new one rather than leaving
 * a socket pointed at a dead process.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { EventStream } from '@/core/sse/client';
import { StreamStatusContext } from '@/core/sse/streamStatus';

interface Props {
  /** From the boot reducer. A change means a different backend process. */
  sessionEpoch: number;
  children: ReactNode;
}

export function EventStreamProvider({ sessionEpoch, children }: Props) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [lastHeartbeatAt, setLastHeartbeatAt] = useState<Date | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);

  useEffect(() => {
    const stream = new EventStream({
      onOpen: () => {
        setConnected(true);
        setLastMessage(null);
      },
      onDisconnect: (reason) => {
        setConnected(false);
        setLastMessage(reason);
      },
      onEvent: (event) => {
        switch (event.name) {
          case 'heartbeat':
            setConnected(true);
            setLastHeartbeatAt(new Date());
            return;
          case 'resync':
            // The server could not cover our `Last-Event-ID`. Everything we
            // hold is suspect, so refetch rather than patch.
            void queryClient.invalidateQueries();
            setLastMessage(`Reconnected (${event.payload.reason}); refetched everything.`);
            return;
        }
      },
    });

    stream.start();
    return () => stream.close();
  }, [queryClient, sessionEpoch]);

  const value = useMemo(
    () => ({ connected, lastHeartbeatAt, lastMessage }),
    [connected, lastHeartbeatAt, lastMessage],
  );

  return <StreamStatusContext.Provider value={value}>{children}</StreamStatusContext.Provider>;
}
