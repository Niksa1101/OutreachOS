import { useQuery } from '@tanstack/react-query';

import { mediaSrc } from '@/core/media/asset-url';

/** Reactive wrapper around `mediaSrc` — re-resolves whenever `absolutePath` changes. */
export function useMediaSrc(absolutePath: string | null | undefined) {
  return useQuery({
    queryKey: ['media-src', absolutePath],
    queryFn: () => mediaSrc(absolutePath as string),
    enabled: absolutePath != null,
    staleTime: Infinity,
  });
}
