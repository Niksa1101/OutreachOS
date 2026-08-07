/**
 * Ticket 22: closing the window while a render is in flight needs confirmation.
 *
 * Pure helpers live here so vitest can cover the decision without a Tauri
 * window. The ShellLayout guard wires them to `onCloseRequested`.
 */

import type { RenderJobSummary, RenderQueueResponse } from '@/core/api/types';

const ACTIVE_STATUSES = new Set(['preparing', 'rendering', 'encoding']);

export function jobIsActivelyRendering(job: Pick<RenderJobSummary, 'status'>): boolean {
  return ACTIVE_STATUSES.has(job.status);
}

export function queueHasActiveRender(queue: Pick<RenderQueueResponse, 'jobs' | 'batch'>): boolean {
  if (typeof queue.batch?.active === 'number') {
    return queue.batch.active > 0;
  }
  return queue.jobs.some(jobIsActivelyRendering);
}

export const CLOSE_DURING_RENDER_MESSAGE =
  'A render is in progress. Closing now will interrupt the current job. Quit anyway?';
