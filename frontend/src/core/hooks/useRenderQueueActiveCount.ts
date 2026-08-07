/**
 * Ticket 18: active-job count for the sidebar badge.
 *
 * Lives in `core/` so `AppSidebar` can show the badge without importing a
 * module. The query key is the literal `['render-queue']` — the same string
 * `EventStreamProvider` invalidates on `render_job_changed` /
 * `batch_progress_changed`, and the same key `renderQueueKeys.list` uses in
 * the video-composer module. Keep those three in sync by hand.
 */

import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import type { RenderQueueResponse } from '@/core/api/types';

export function useRenderQueueActiveCount(): number {
  const { data } = useQuery({
    queryKey: ['render-queue'],
    queryFn: () => apiFetch<RenderQueueResponse>('/render-queue'),
    // Badge is decorative; don't fight the queue screen for focus.
    select: (response) => response.batch.active_job_count,
  });

  return data ?? 0;
}
