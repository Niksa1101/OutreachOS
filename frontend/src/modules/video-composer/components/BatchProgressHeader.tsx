/**
 * Ticket 18: batch-level progress and ETA above the queue table.
 * Ticket 20: when the queue drains, a completed/failed summary with Retry failed.
 */

import type { BatchProgress } from '@/core/api/types';
import { Button } from '@/core/components/ui/button';
import { Progress, ProgressLabel, ProgressValue } from '@/core/components/ui/progress';
import { useRetryFailedJobs } from '@/modules/video-composer/api/queue';
import {
  formatBatchCompletionSummary,
  formatBatchCounts,
  formatEta,
} from '@/modules/video-composer/lib/batch-progress';

interface Props {
  batch: BatchProgress;
}

export function BatchProgressHeader({ batch }: Props) {
  const retryFailed = useRetryFailedJobs();

  if (batch.total === 0) {
    return null;
  }

  const idle = batch.active_job_count === 0;
  const etaSeconds = batch.eta_seconds ?? null;
  const showRetry = idle && batch.failed > 0;

  return (
    <div className="mt-4 rounded-xl border border-border px-4 py-3">
      <Progress value={batch.progress_pct} className="w-full">
        <div className="flex w-full items-baseline justify-between gap-3">
          <ProgressLabel>This run</ProgressLabel>
          <ProgressValue>
            {() => `${Math.round(batch.progress_pct)}% · ${formatBatchCounts(batch)}`}
          </ProgressValue>
        </div>
      </Progress>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {idle ? formatBatchCompletionSummary(batch) : formatEta(etaSeconds)}
        </p>
        {showRetry ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={retryFailed.isPending}
            onClick={() => {
              retryFailed.mutate();
            }}
          >
            {retryFailed.isPending ? 'Retrying…' : 'Retry failed'}
          </Button>
        ) : null}
      </div>
      {retryFailed.isError ? (
        <p className="mt-2 text-xs text-destructive">Could not retry failed jobs.</p>
      ) : null}
    </div>
  );
}
