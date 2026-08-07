/**
 * Ticket 20: plain-language failure on the row; stderr + pasteable command
 * behind one expansion.
 */

import { ChevronDown } from 'lucide-react';

import type { RenderJobSummary } from '@/core/api/types';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/core/components/ui/collapsible';

interface Props {
  job: RenderJobSummary;
}

export function FailedJobDetails({ job }: Props) {
  if (job.status !== 'failed' || !job.error_message) {
    return null;
  }

  const hasTechnical = Boolean(job.error_details || job.ffmpeg_command);

  return (
    <div className="mt-1 max-w-md space-y-1">
      <p className="text-xs text-destructive">{job.error_message}</p>
      {hasTechnical ? (
        <Collapsible>
          <CollapsibleTrigger className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground [&[data-panel-open]_svg]:rotate-180">
            Technical details
            <ChevronDown className="size-3 transition-transform" />
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-1 space-y-2">
            {job.ffmpeg_command ? (
              <div>
                <p className="mb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  Command
                </p>
                <pre className="overflow-x-auto rounded-md bg-muted/60 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-foreground">
                  {job.ffmpeg_command}
                </pre>
              </div>
            ) : null}
            {job.error_details ? (
              <div>
                <p className="mb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  FFmpeg output
                </p>
                <pre className="max-h-48 overflow-auto rounded-md bg-muted/60 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-foreground">
                  {job.error_details}
                </pre>
              </div>
            ) : null}
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </div>
  );
}
