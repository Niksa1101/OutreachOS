import { Lock } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import { Button } from '@/core/components/ui/button';
import { InlineError } from '@/core/ui/InlineError';
import { useCancelQueue } from '@/modules/video-composer/api/campaigns';

interface Props {
  campaignId: string;
  reason: string;
}

/**
 * Ticket 21: shown whenever `CampaignDetail.is_locked` is true. `Cancel
 * Queue` is the only way out — it clears the campaign's queued/active jobs
 * server-side, which is also what `is_campaign_locked` reads, so a
 * successful cancel unlocks the editor in the same response.
 */
export function EditorLockBanner({ campaignId, reason }: Props) {
  const cancelQueue = useCancelQueue();

  return (
    <section
      className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3"
      aria-live="polite"
      role="status"
    >
      <div className="flex items-center gap-3">
        <Lock aria-hidden className="size-4 shrink-0 text-amber-600" />
        <p className="min-w-0 flex-1 text-sm font-medium text-amber-950 dark:text-amber-100">
          {reason}
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={cancelQueue.isPending}
          onClick={() => cancelQueue.mutate(campaignId)}
        >
          Cancel Queue
        </Button>
      </div>
      <InlineError
        message={cancelQueue.error ? errorMessage(cancelQueue.error) : null}
        className="mt-2 text-xs text-destructive"
      />
    </section>
  );
}
