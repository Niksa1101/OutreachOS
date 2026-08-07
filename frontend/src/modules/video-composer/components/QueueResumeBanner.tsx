import { PauseCircle } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import { Button } from '@/core/components/ui/button';
import { InlineError } from '@/core/ui/InlineError';
import { useResumeRenderQueue } from '@/modules/video-composer/api/queue';

/**
 * Ticket 22: shown when the queue came back paused after a crash/close.
 * Resume is the only way work starts again — nothing auto-restarts.
 */
export function QueueResumeBanner() {
  const resume = useResumeRenderQueue();

  return (
    <section
      className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3"
      aria-live="polite"
      role="status"
    >
      <div className="flex items-center gap-3">
        <PauseCircle aria-hidden className="size-4 shrink-0 text-amber-600" />
        <p className="min-w-0 flex-1 text-sm font-medium text-amber-950 dark:text-amber-100">
          The queue was interrupted. Waiting jobs were preserved; resume when you are ready to
          continue.
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={resume.isPending}
          onClick={() => resume.mutate()}
        >
          Resume
        </Button>
      </div>
      <InlineError
        message={resume.error ? errorMessage(resume.error) : null}
        className="mt-2 text-xs text-destructive"
      />
    </section>
  );
}
