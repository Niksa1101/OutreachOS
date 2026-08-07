/**
 * Ticket 22: intercept window close while a render job is in flight.
 *
 * Uses Tauri's `onCloseRequested` + the dialog plugin. Outside a Tauri webview
 * (plain `vite` in a browser) the APIs are absent and this is a no-op.
 */

import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import type { RenderQueueResponse } from '@/core/api/types';
import {
  CLOSE_DURING_RENDER_MESSAGE,
  queueHasActiveRender,
} from '@/core/layout/closeDuringRender';

export function CloseDuringRenderGuard() {
  const queryClient = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;

    void (async () => {
      try {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const { ask } = await import('@tauri-apps/plugin-dialog');
        if (cancelled) return;

        const window = getCurrentWindow();
        unlisten = await window.onCloseRequested(async (event) => {
          let queue =
            queryClient.getQueryData<RenderQueueResponse>(['render-queue']) ?? null;
          try {
            queue = await apiFetch<RenderQueueResponse>('/render-queue');
            queryClient.setQueryData(['render-queue'], queue);
          } catch {
            // Prefer a fresh read; if the backend is already gone, fall back to
            // the last known cache so we still warn when we can.
          }

          if (!queue || !queueHasActiveRender(queue)) {
            return;
          }

          const confirmed = await ask(CLOSE_DURING_RENDER_MESSAGE, {
            title: 'OutreachOS',
            kind: 'warning',
          });
          if (!confirmed) {
            event.preventDefault();
          }
        });
      } catch {
        // Browser / non-Tauri — nothing to wire.
      }
    })();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [queryClient]);

  return null;
}
