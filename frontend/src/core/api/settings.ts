/**
 * Settings API — ticket 25.
 */

import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import { queryKeys } from '@/core/api/queries';
import type {
  ClearCacheResponse,
  SettingsResponse,
  SettingsUpdateRequest,
} from '@/core/api/types';

export const useUpdateSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsUpdateRequest) =>
      apiFetch<SettingsResponse>('/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.settings, data);
    },
  });
};

export const useClearCache = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ClearCacheResponse>('/settings/clear-cache', {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
};

export const settingsQueryOptions = queryOptions({
  queryKey: queryKeys.settings,
  queryFn: () => apiFetch<SettingsResponse>('/settings'),
});
