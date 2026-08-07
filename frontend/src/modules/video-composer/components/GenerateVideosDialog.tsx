import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { errorMessage } from '@/core/api/error-message';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/core/components/ui/alert-dialog';
import { Button } from '@/core/components/ui/button';
import { Skeleton } from '@/core/components/ui/skeleton';
import { InlineError } from '@/core/ui/InlineError';
import {
  campaignGeneratePlanQuery,
  useGenerateVideos,
} from '@/modules/video-composer/api/queue';

interface Props {
  campaignId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onQueued?: (notice: string | null) => void;
}

function describePlan(
  renderCount: number,
  skipCount: number,
  alreadyQueuedCount: number,
  allCurrent: boolean,
): string {
  if (allCurrent) {
    return 'Every recording is already up to date. Generate would skip all of them.';
  }
  if (renderCount === 0 && alreadyQueuedCount > 0) {
    return alreadyQueuedCount === 1
      ? '1 recording is already queued. Generate would enqueue nothing.'
      : `${alreadyQueuedCount} recordings are already queued. Generate would enqueue nothing.`;
  }
  const renderPart =
    renderCount === 1 ? '1 recording will render' : `${renderCount} recordings will render`;
  const extras: string[] = [];
  if (skipCount > 0) {
    extras.push(
      skipCount === 1
        ? '1 already current will be skipped'
        : `${skipCount} already current will be skipped`,
    );
  }
  if (alreadyQueuedCount > 0) {
    extras.push(
      alreadyQueuedCount === 1
        ? '1 is already queued'
        : `${alreadyQueuedCount} are already queued`,
    );
  }
  if (extras.length === 0) {
    return `${renderPart}. None are already current.`;
  }
  return `${renderPart}. ${extras.join('. ')}.`;
}

export function GenerateVideosDialog({ campaignId, open, onOpenChange, onQueued }: Props) {
  const generateVideos = useGenerateVideos();
  const [actionError, setActionError] = useState<string | null>(null);
  const plan = useQuery({
    ...campaignGeneratePlanQuery(campaignId),
    enabled: open,
  });

  const busy = generateVideos.isPending;

  function enqueue(force: boolean) {
    setActionError(null);
    generateVideos.mutate(
      { campaignId, force },
      {
        onSuccess: (result) => {
          onOpenChange(false);
          if (result.all_current) {
            onQueued?.('Every recording is already up to date — nothing was queued.');
            return;
          }
          if (result.alpha_cache_warm) {
            onQueued?.('Overlay clip reused from cache — encoding starts immediately.');
            return;
          }
          onQueued?.(null);
        },
        onError: (error) => setActionError(errorMessage(error)),
      },
    );
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Generate videos?</AlertDialogTitle>
          <AlertDialogDescription>
            Already-rendered recordings are skipped unless you choose Re-render All. That
            tracking lives on each recording, so it still applies after an export clears the
            queue.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {plan.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        ) : plan.isError ? (
          <p className="text-sm text-destructive">
            Could not load what would be queued. Try again in a moment.
          </p>
        ) : plan.data ? (
          <p className="text-sm text-foreground" role="status">
            {describePlan(
              plan.data.render_count,
              plan.data.skip_count,
              plan.data.already_queued_count,
              plan.data.all_current,
            )}
            {plan.data.alpha_cache_warm
              ? ' The overlay clip is already cached.'
              : plan.data.render_count > 0
                ? ' The overlay clip will be prepared first.'
                : null}
          </p>
        ) : null}

        <InlineError message={actionError} className="text-sm text-destructive" />

        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <Button
            type="button"
            variant="outline"
            disabled={
              plan.isPending ||
              plan.isError ||
              busy ||
              (plan.data != null &&
                plan.data.render_count + plan.data.skip_count === 0)
            }
            onClick={() => enqueue(true)}
          >
            {busy ? 'Queuing…' : 'Re-render All'}
          </Button>
          <Button
            type="button"
            disabled={
              plan.isPending ||
              plan.isError ||
              busy ||
              plan.data?.render_count === 0
            }
            onClick={() => enqueue(false)}
          >
            {busy ? 'Queuing…' : 'Generate Videos'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
