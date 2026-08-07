/** Formatting helpers for ticket 18's batch progress / ETA header. */

export function formatEta(etaSeconds: number | null): string {
  if (etaSeconds === null) {
    return 'Estimating…';
  }
  if (etaSeconds <= 0) {
    return 'Done';
  }

  if (etaSeconds < 60) {
    return `~${etaSeconds}s left`;
  }

  const minutes = Math.floor(etaSeconds / 60);
  const seconds = etaSeconds % 60;
  if (minutes < 60) {
    return seconds === 0 ? `~${minutes}m left` : `~${minutes}m ${seconds}s left`;
  }

  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return remMinutes === 0 ? `~${hours}h left` : `~${hours}h ${remMinutes}m left`;
}

export function formatBatchCounts(batch: {
  completed: number;
  failed: number;
  total: number;
}): string {
  const finished = batch.completed + batch.failed;
  if (batch.failed > 0) {
    return `${finished} of ${batch.total} · ${batch.failed} failed`;
  }
  return `${finished} of ${batch.total}`;
}

/** Idle-queue summary — matches PRD §6.4's "28 completed, 2 failed" phrasing. */
export function formatBatchCompletionSummary(batch: {
  completed: number;
  failed: number;
}): string {
  if (batch.failed === 0) {
    return batch.completed === 1
      ? '1 completed — queue idle.'
      : `${batch.completed} completed — queue idle.`;
  }
  return `${batch.completed} completed, ${batch.failed} failed`;
}
