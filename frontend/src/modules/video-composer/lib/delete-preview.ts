/** Human-readable byte counts for delete confirmation line items. */

import { formatBytes, plural } from '@/core/lib/format';

export { formatBytes, plural };

export function describeCampaignData(
  assetCount: number,
  recordingCount: number,
  talkingHeadCount: number,
): string {
  if (assetCount === 0) {
    return 'Campaign settings and overlay configuration';
  }

  const parts: string[] = [];
  if (talkingHeadCount > 0) {
    parts.push(`${talkingHeadCount} ${plural(talkingHeadCount, 'talking head')}`);
  }
  if (recordingCount > 0) {
    parts.push(`${recordingCount} ${plural(recordingCount, 'recording reference')}`);
  }

  if (parts.length === 0) {
    return `${assetCount} ${plural(assetCount, 'asset reference')}`;
  }

  return `Campaign data (${parts.join(', ')})`;
}

export function describeAlphaClip(present: boolean, sizeBytes: number | null | undefined): string {
  if (!present) return 'No cached alpha clip';
  return `Cached alpha clip (${formatBytes(sizeBytes ?? 0)})`;
}

export function describeOutputs(
  count: number,
  totalSizeBytes: number,
  noun: 'output' | 'render' = 'output',
): string {
  if (count === 0) {
    return noun === 'render'
      ? 'No un-exported renders in staging.'
      : 'No un-exported outputs';
  }
  return `${count} un-exported ${plural(count, noun)} (${formatBytes(totalSizeBytes)})`;
}
