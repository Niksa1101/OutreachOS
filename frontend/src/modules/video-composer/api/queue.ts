/**
 * TanStack Query hooks for the global Render Queue (tickets 15 / 17 / 19 / 22).
 *
 * `queryKey: ['render-queue']` is a literal, not `campaignQueryKeys`-derived:
 * `EventStreamProvider.tsx` patches (or cold-cache invalidates) this exact key
 * on `render_job_changed` / `batch_progress_changed` and cannot import from
 * this module (cross-module imports are lint-forbidden), so the two must be
 * kept in sync by hand.
 */

import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import type {
  GeneratePlanResponse,
  GenerateVideosResponse,
  RenderQueueResponse,
  RetryFailedResponse,
} from '@/core/api/types';
import { campaignQueryKeys } from '@/modules/video-composer/api/campaigns';

export const renderQueueKeys = {
  list: ['render-queue'] as const,
};

export const renderQueueQuery = queryOptions({
  queryKey: renderQueueKeys.list,
  queryFn: () => apiFetch<RenderQueueResponse>('/render-queue'),
});

export const campaignGeneratePlanQuery = (campaignId: string) =>
  queryOptions({
    queryKey: [...campaignQueryKeys.detail(campaignId), 'generate-plan'] as const,
    queryFn: () => apiFetch<GeneratePlanResponse>(`/campaigns/${campaignId}/generate-plan`),
  });

function useSetRenderQueueCache() {
  const queryClient = useQueryClient();
  return (result: RenderQueueResponse) => {
    queryClient.setQueryData(renderQueueKeys.list, result);
    void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
  };
}

export function useGenerateVideos() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, force = false }: { campaignId: string; force?: boolean }) =>
      apiFetch<GenerateVideosResponse>(`/campaigns/${campaignId}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force }),
      }),
    onSuccess: (_result, { campaignId }) => {
      void queryClient.invalidateQueries({ queryKey: renderQueueKeys.list });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.detail(campaignId) });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

/** Ticket 19: stop claiming the next job; the in-flight job finishes. */
export function usePauseRenderQueue() {
  const setCache = useSetRenderQueueCache();

  return useMutation({
    mutationFn: () =>
      apiFetch<RenderQueueResponse>('/render-queue/pause', {
        method: 'POST',
      }),
    onSuccess: setCache,
  });
}

/** Ticket 19/22: clear a crash-recovery (or user) pause and let the worker claim. */
export function useResumeRenderQueue() {
  const setCache = useSetRenderQueueCache();

  return useMutation({
    mutationFn: () =>
      apiFetch<RenderQueueResponse>('/render-queue/resume', {
        method: 'POST',
      }),
    onSuccess: setCache,
  });
}

/** Ticket 19: cancel one queued or active job. */
export function useCancelRenderJob() {
  const setCache = useSetRenderQueueCache();

  return useMutation({
    mutationFn: (jobId: string) =>
      apiFetch<RenderQueueResponse>(`/render-queue/jobs/${jobId}/cancel`, {
        method: 'POST',
      }),
    onSuccess: setCache,
  });
}

/** Ticket 19: retry one failed job. */
export function useRetryRenderJob() {
  const setCache = useSetRenderQueueCache();

  return useMutation({
    mutationFn: (jobId: string) =>
      apiFetch<RenderQueueResponse>(`/render-queue/jobs/${jobId}/retry`, {
        method: 'POST',
      }),
    onSuccess: setCache,
  });
}

/** Ticket 19: persist a new global order. */
export function useReorderRenderQueue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobIds: string[]) =>
      apiFetch<RenderQueueResponse>('/render-queue/reorder', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_ids: jobIds }),
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(renderQueueKeys.list, result);
    },
  });
}

/** Ticket 20: re-enqueue every failed job; leave completed rows alone. */
export function useRetryFailedJobs() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiFetch<RetryFailedResponse>('/render-queue/retry-failed', {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: renderQueueKeys.list });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}
