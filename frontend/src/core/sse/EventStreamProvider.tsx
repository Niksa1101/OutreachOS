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

import { primeBackendInfo } from '@/core/api/client';
import type { RenderQueueResponse } from '@/core/api/types';
import { EventStream } from '@/core/sse/client';
import type { RenderJobPayload } from '@/core/sse/events';
import { StreamStatusContext } from '@/core/sse/streamStatus';

interface Props {
  /** From the boot reducer. A change means a different backend process. */
  sessionEpoch: number;
  children: ReactNode;
}

const RENDER_QUEUE_KEY = ['render-queue'] as const;

function patchRenderQueueJob(
  cached: RenderQueueResponse,
  job: RenderJobPayload,
): RenderQueueResponse {
  const jobs = cached.jobs.some((row) => row.id === job.id)
    ? cached.jobs.map((row) => (row.id === job.id ? job : row))
    : [...cached.jobs, job];
  return { ...cached, jobs };
}

export function EventStreamProvider({ sessionEpoch, children }: Props) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [lastHeartbeatAt, setLastHeartbeatAt] = useState<Date | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);

  useEffect(() => {
    let stream: EventStream | null = null;
    let cancelled = false;

    void (async () => {
      // Must complete before `start()`. BootSync also calls this on
      // `sessionEpoch`, but both paths share the same deduped invoke — and
      // awaiting here removes the race where the shell mounts first.
      await primeBackendInfo();
      if (cancelled) return;

      stream = new EventStream({
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
            case 'campaign_lock_changed':
              // Targeted rather than a blanket invalidate: this key shape
              // mirrors `campaignQueryKeys.detail` in
              // `modules/video-composer/api/campaigns.ts`, which `core` may
              // not import (cross-module imports are lint-forbidden).
              void queryClient.invalidateQueries({
                queryKey: ['campaigns', 'detail', event.payload.campaign_id],
              });
              return;
            case 'render_job_changed': {
              // Event docstrings promise a full row so listeners can patch.
              // Fall back to invalidate when cold (sidebar badge shares this key).
              const cached = queryClient.getQueryData<RenderQueueResponse>(RENDER_QUEUE_KEY);
              if (!cached) {
                void queryClient.invalidateQueries({ queryKey: RENDER_QUEUE_KEY });
                void queryClient.invalidateQueries({
                  queryKey: ['campaigns', 'detail', event.payload.job.campaign_id],
                });
                return;
              }
              const job = event.payload.job;
              const previous = cached.jobs.find((row) => row.id === job.id);
              const statusChanged = previous?.status !== job.status;
              queryClient.setQueryData(RENDER_QUEUE_KEY, patchRenderQueueJob(cached, job));
              // Progress ticks must not refetch campaign detail; status
              // transitions (lock, completion) still do.
              if (statusChanged) {
                void queryClient.invalidateQueries({
                  queryKey: ['campaigns', 'detail', job.campaign_id],
                });
              }
              return;
            }
            case 'batch_progress_changed': {
              const cached = queryClient.getQueryData<RenderQueueResponse>(RENDER_QUEUE_KEY);
              if (!cached) {
                void queryClient.invalidateQueries({ queryKey: RENDER_QUEUE_KEY });
                return;
              }
              queryClient.setQueryData(RENDER_QUEUE_KEY, {
                ...cached,
                batch: event.payload.batch,
              });
              return;
            }
          }
        },
      });

      stream.start();
    })();

    return () => {
      cancelled = true;
      stream?.close();
    };
  }, [queryClient, sessionEpoch]);

  const value = useMemo(
    () => ({ connected, lastHeartbeatAt, lastMessage }),
    [connected, lastHeartbeatAt, lastMessage],
  );

  return <StreamStatusContext.Provider value={value}>{children}</StreamStatusContext.Provider>;
}
