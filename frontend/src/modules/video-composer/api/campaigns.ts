/**
 * TanStack Query hooks for campaign CRUD.
 *
 * Module-owned API layer: imports the typed client from core, never the other
 * way around.
 */

import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import type {
  ApplyPresetRequest,
  AssetRelocateRequest,
  CampaignCreateRequest,
  CampaignDeletePreview,
  CampaignDetail,
  CampaignListResponse,
  CampaignUpdateRequest,
  OverlayConfigDto,
  OverlayPresetCreateRequest,
  OverlayPresetDetail,
  OverlayPresetListResponse,
  OverlayPresetRenameRequest,
  OverlayPresetSummary,
  PreviewFrameResponse,
  RecordingImportRequest,
  RecordingImportResponse,
  RecordingDetail,
  RecordingUpdateRequest,
  TalkingHeadAssignRequest,
  TalkingHeadTrimRequest,
} from '@/core/api/types';

export const campaignQueryKeys = {
  all: ['campaigns'] as const,
  list: ['campaigns', 'list'] as const,
  detail: (id: string) => ['campaigns', 'detail', id] as const,
  previewFrame: (id: string) => ['campaigns', 'detail', id, 'preview-frame'] as const,
};

export const presetQueryKeys = {
  all: ['overlay-presets'] as const,
  list: ['overlay-presets', 'list'] as const,
};

export const presetsListQuery = queryOptions({
  queryKey: presetQueryKeys.list,
  queryFn: () => apiFetch<OverlayPresetListResponse>('/overlay-presets'),
});

export const campaignsListQuery = queryOptions({
  queryKey: campaignQueryKeys.list,
  queryFn: () => apiFetch<CampaignListResponse>('/campaigns'),
});

export const campaignDetailQuery = (id: string) =>
  queryOptions({
    queryKey: campaignQueryKeys.detail(id),
    queryFn: () => apiFetch<CampaignDetail>(`/campaigns/${id}`),
  });

/**
 * The split-view preview's background frame (ticket 09). Its own query,
 * separate from `campaignDetailQuery`, because extraction can shell out to
 * FFmpeg on a cache miss — campaign detail's own side effect (link-health
 * verification) is a plain `stat()`, and folding this in would make every
 * detail fetch pay for a frame nothing asked to see yet.
 */
export const campaignPreviewFrameQuery = (id: string) =>
  queryOptions({
    queryKey: campaignQueryKeys.previewFrame(id),
    queryFn: () => apiFetch<PreviewFrameResponse>(`/campaigns/${id}/preview-frame`),
  });

export const campaignDeletePreviewQuery = (id: string) =>
  queryOptions({
    queryKey: [...campaignQueryKeys.detail(id), 'delete-preview'] as const,
    queryFn: () => apiFetch<CampaignDeletePreview>(`/campaigns/${id}/delete-preview`),
  });

export function useCreateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: CampaignCreateRequest = {}) =>
      apiFetch<CampaignDetail>('/campaigns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useRenameCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, name }: CampaignUpdateRequest & { id: string }) =>
      apiFetch<CampaignDetail>(`/campaigns/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useDuplicateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<CampaignDetail>(`/campaigns/${id}/duplicate`, {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/campaigns/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useUpdateOverlayConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, overlay }: { campaignId: string; overlay: OverlayConfigDto }) =>
      apiFetch<CampaignDetail>(`/campaigns/${campaignId}/overlay`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(overlay),
      }),
    onSuccess: (detail) => {
      queryClient.setQueryData(campaignQueryKeys.detail(detail.id), detail);
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useAssignTalkingHead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, ...body }: TalkingHeadAssignRequest & { campaignId: string }) =>
      apiFetch<CampaignDetail>(`/campaigns/${campaignId}/talking-head`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (detail) => {
      queryClient.setQueryData(campaignQueryKeys.detail(detail.id), detail);
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useUpdateTalkingHeadTrim() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, ...body }: TalkingHeadTrimRequest & { campaignId: string }) =>
      apiFetch<CampaignDetail>(`/campaigns/${campaignId}/talking-head/trim`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (detail) => {
      queryClient.setQueryData(campaignQueryKeys.detail(detail.id), detail);
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useImportRecordings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, ...body }: RecordingImportRequest & { campaignId: string }) =>
      apiFetch<RecordingImportResponse>(`/campaigns/${campaignId}/recordings/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({
        queryKey: campaignQueryKeys.detail(variables.campaignId),
      });
      void queryClient.invalidateQueries({
        queryKey: campaignQueryKeys.previewFrame(variables.campaignId),
      });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

function patchCampaignRecording(
  queryClient: ReturnType<typeof useQueryClient>,
  campaignId: string,
  recordingId: string,
  updater: (recording: RecordingDetail) => RecordingDetail,
) {
  queryClient.setQueryData<CampaignDetail>(campaignQueryKeys.detail(campaignId), (current) => {
    if (!current) {
      return current;
    }

    const recordings = (current.recordings ?? []).map((recording) =>
      recording.id === recordingId ? updater(recording) : recording,
    );

    return { ...current, recordings };
  });
}

export function useUpdateRecording() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      campaignId,
      recordingId,
      ...body
    }: RecordingUpdateRequest & { campaignId: string; recordingId: string }) =>
      apiFetch<RecordingDetail>(`/campaigns/${campaignId}/recordings/${recordingId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (updated, variables) => {
      patchCampaignRecording(
        queryClient,
        variables.campaignId,
        variables.recordingId,
        () => updated,
      );
      void queryClient.invalidateQueries({
        queryKey: campaignQueryKeys.detail(variables.campaignId),
      });
    },
  });
}

export function useDeleteRecording() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, recordingId }: { campaignId: string; recordingId: string }) =>
      apiFetch<void>(`/campaigns/${campaignId}/recordings/${recordingId}`, {
        method: 'DELETE',
      }),
    onSuccess: (_result, variables) => {
      queryClient.setQueryData<CampaignDetail>(
        campaignQueryKeys.detail(variables.campaignId),
        (current) => {
          if (!current) {
            return current;
          }

          const recordings = (current.recordings ?? []).filter(
            (recording) => recording.id !== variables.recordingId,
          );

          return {
            ...current,
            recordings,
            recording_count: recordings.length,
          };
        },
      );
      void queryClient.invalidateQueries({
        queryKey: campaignQueryKeys.detail(variables.campaignId),
      });
      void queryClient.invalidateQueries({
        queryKey: campaignQueryKeys.previewFrame(variables.campaignId),
      });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useCancelQueue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (campaignId: string) =>
      apiFetch<CampaignDetail>(`/campaigns/${campaignId}/cancel-queue`, {
        method: 'POST',
      }),
    onSuccess: (detail) => {
      queryClient.setQueryData(campaignQueryKeys.detail(detail.id), detail);
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
      // Ticket 19: Cancel Queue clears jobs the queue screen also shows.
      void queryClient.invalidateQueries({ queryKey: ['render-queue'] });
    },
  });
}

export function useApplyPreset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, ...body }: ApplyPresetRequest & { campaignId: string }) =>
      apiFetch<CampaignDetail>(`/campaigns/${campaignId}/apply-preset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (detail) => {
      queryClient.setQueryData(campaignQueryKeys.detail(detail.id), detail);
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}

export function useCreatePreset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: OverlayPresetCreateRequest) =>
      apiFetch<OverlayPresetDetail>('/overlay-presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: presetQueryKeys.all });
    },
  });
}

export function useRenamePreset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, name }: OverlayPresetRenameRequest & { id: string }) =>
      apiFetch<OverlayPresetSummary>(`/overlay-presets/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: presetQueryKeys.all });
    },
  });
}

export function useDeletePreset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/overlay-presets/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: presetQueryKeys.all });
    },
  });
}

export function useRelocateAsset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      campaignId,
      assetId,
      ...body
    }: AssetRelocateRequest & { campaignId: string; assetId: string }) =>
      apiFetch<CampaignDetail>(`/campaigns/${campaignId}/assets/${assetId}/relocate`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (detail) => {
      queryClient.setQueryData(campaignQueryKeys.detail(detail.id), detail);
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.previewFrame(detail.id) });
      void queryClient.invalidateQueries({ queryKey: campaignQueryKeys.all });
    },
  });
}
