/** Human-readable byte counts for delete confirmation line items. */

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  const formatted = value >= 10 || exponent === 0 ? value.toFixed(0) : value.toFixed(1);

  return `${formatted} ${units[exponent]}`;
}

function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return count === 1 ? singular : pluralForm;
}

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

export function describeOutputs(count: number, totalSizeBytes: number): string {
  if (count === 0) return 'No un-exported outputs';
  return `${count} un-exported ${plural(count, 'output')} (${formatBytes(totalSizeBytes)})`;
}
