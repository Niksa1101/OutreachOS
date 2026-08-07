/**
 * TanStack Query hooks for campaign outputs and Export All (ticket 23).
 */

import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import type { CampaignOutputsResponse, ExportAllRequest, ExportAllResponse } from '@/core/api/types';
import { campaignQueryKeys } from '@/modules/video-composer/api/campaigns';
import { renderQueueKeys } from '@/modules/video-composer/api/queue';

export const campaignOutputsQuery = (campaignId: string) =>
  queryOptions({
    queryKey: [...campaignQueryKeys.detail(campaignId), 'outputs'] as const,
    queryFn: () => apiFetch<CampaignOutputsResponse>(`/campaigns/${campaignId}/outputs`),
  });

export function useExportAll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      campaignId,
      destination_path,
    }: ExportAllRequest & { campaignId: string }) =>
      apiFetch<ExportAllResponse>(`/campaigns/${campaignId}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ destination_path }),
      }),
    onSuccess: (_result, { campaignId }) => {
      void queryClient.invalidateQueries({
        queryKey: [...campaignQueryKeys.detail(campaignId), 'outputs'],
      });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.detail(campaignId) });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: renderQueueKeys.list });
    },
  });
}
