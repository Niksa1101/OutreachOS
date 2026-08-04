/**
 * TanStack Query bindings for the P0 endpoints.
 *
 * Tech.md §3.2: TanStack Query owns everything from the API. SSE events
 * invalidate or patch the cache; nothing hand-rolls fetching.
 *
 * The query keys are namespaced but carry no `boot_id`. A new backend session
 * clears the whole cache (Q78) rather than being keyed around, because a stale
 * entry from a dead process is not something you want to be able to read at
 * all — even under a key nobody looks up.
 */

import { queryOptions } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import type { SettingsResponse } from '@/core/api/types';

export const queryKeys = {
  settings: ['settings'] as const,
};

export const settingsQuery = queryOptions({
  queryKey: queryKeys.settings,
  queryFn: () => apiFetch<SettingsResponse>('/settings'),
});
