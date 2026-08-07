/** Human-readable copy for the Outputs section and Export All flow. */

import { describeOutputs } from '@/modules/video-composer/lib/delete-preview';

export function describeExportableCount(exportableCount: number): string {
  if (exportableCount === 0) {
    return 'No completed renders are ready to export yet.';
  }
  return exportableCount === 1
    ? '1 completed render is ready to export.'
    : `${exportableCount} completed renders are ready to export.`;
}

export function describeExportConfirmation(
  exportableCount: number,
  destinationPath: string,
): string {
  const filePart =
    exportableCount === 1
      ? '1 file will move'
      : `${exportableCount} files will move`;
  return `${filePart} to ${destinationPath}. Existing files at the destination are never overwritten.`;
}

export function describeStagedOutputs(count: number, totalSizeBytes: number): string {
  return describeOutputs(count, totalSizeBytes, 'render');
}

export function describeExportResult(
  movedCount: number,
  conflicts: string[],
  failures: Array<{ filename: string; reason: string }> = [],
): string | null {
  if (movedCount === 0 && conflicts.length === 0 && failures.length === 0) {
    return 'Nothing was exported — no completed renders were ready.';
  }

  const parts: string[] = [];
  if (movedCount > 0) {
    parts.push(
      movedCount === 1
        ? '1 file exported.'
        : `${movedCount} files exported.`,
    );
  }
  if (conflicts.length > 0) {
    const names = conflicts.join(', ');
    parts.push(
      conflicts.length === 1
        ? `1 file was skipped because it already exists at the destination: ${names}.`
        : `${conflicts.length} files were skipped because they already exist at the destination: ${names}.`,
    );
  }
  if (failures.length > 0) {
    const names = failures.map((failure) => failure.filename).join(', ');
    parts.push(
      failures.length === 1
        ? `1 file could not be moved: ${names}.`
        : `${failures.length} files could not be moved: ${names}.`,
    );
  }
  return parts.join(' ');
}
