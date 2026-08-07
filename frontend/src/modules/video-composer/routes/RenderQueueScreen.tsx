/**
 * Render Queue — every job, from every campaign, ordered by queue position.
 *
 * Ticket 19: pause / resume, per-job cancel & retry, and drag reorder (dnd-kit).
 * The actively encoding (or otherwise in-flight) job is pinned. Progress and
 * status arrive over SSE via `render_job_changed` / `batch_progress_changed`.
 */

import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useQuery } from '@tanstack/react-query';
import { GripVertical, ListVideo, Pause, Play } from 'lucide-react';
import { useState } from 'react';

import { errorMessage } from '@/core/api/error-message';
import type { RenderJobSummary } from '@/core/api/types';
import { Button } from '@/core/components/ui/button';
import { Skeleton } from '@/core/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/core/components/ui/table';
import { EmptyState } from '@/core/ui/EmptyState';
import { InlineError } from '@/core/ui/InlineError';
import {
  renderQueueQuery,
  useCancelRenderJob,
  usePauseRenderQueue,
  useReorderRenderQueue,
  useResumeRenderQueue,
  useRetryRenderJob,
} from '@/modules/video-composer/api/queue';
import { BatchProgressHeader } from '@/modules/video-composer/components/BatchProgressHeader';
import { FailedJobDetails } from '@/modules/video-composer/components/FailedJobDetails';
import { QueueResumeBanner } from '@/modules/video-composer/components/QueueResumeBanner';

const JOB_TYPE_LABELS: Record<string, string> = {
  alpha_prepare: 'Prepare overlay',
  video_render: 'Render video',
};

const STATUS_LABELS: Record<string, string> = {
  waiting: 'Waiting',
  preparing: 'Preparing',
  rendering: 'Rendering',
  encoding: 'Encoding',
  completed: 'Completed',
  failed: 'Failed',
};

const STATUS_CLASSES: Record<string, string> = {
  waiting: 'bg-muted text-muted-foreground',
  preparing: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  rendering: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  encoding: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  completed: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  failed: 'bg-destructive/15 text-destructive',
};

function isInFlight(job: RenderJobSummary): boolean {
  return job.status === 'preparing' || job.status === 'rendering' || job.status === 'encoding';
}

function canCancel(job: RenderJobSummary): boolean {
  return (
    job.status === 'waiting' ||
    job.status === 'preparing' ||
    job.status === 'rendering' ||
    job.status === 'encoding'
  );
}

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        STATUS_CLASSES[status] ?? 'bg-muted text-muted-foreground'
      }`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function ProgressBar({ job }: { job: RenderJobSummary }) {
  if (!isInFlight(job)) {
    return null;
  }

  return (
    <div className="mt-1 h-1.5 w-full max-w-32 overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-primary transition-[width]"
        style={{ width: `${Math.min(100, Math.max(0, job.progress_pct))}%` }}
      />
    </div>
  );
}

interface SortableRowProps {
  job: RenderJobSummary;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  busy: boolean;
}

function SortableJobRow({ job, onCancel, onRetry, busy }: SortableRowProps) {
  const pinned = isInFlight(job);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: job.id,
    disabled: pinned,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <TableRow
      ref={setNodeRef}
      style={style}
      className={[
        job.job_type === 'alpha_prepare' ? 'border-l-2 border-l-primary/60 bg-muted/20' : '',
        isDragging ? 'opacity-80 shadow-md' : '',
        pinned ? 'bg-muted/10' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <TableCell className="w-10">
        {pinned ? (
          <span className="inline-flex size-8 items-center justify-center text-muted-foreground/40">
            <GripVertical className="size-4" aria-hidden />
          </span>
        ) : (
          <button
            type="button"
            className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={`Reorder ${job.output_filename ?? job.job_type}`}
            {...attributes}
            {...listeners}
          >
            <GripVertical className="size-4" />
          </button>
        )}
      </TableCell>
      <TableCell className="font-medium">{job.campaign_name}</TableCell>
      <TableCell className="text-muted-foreground">
        {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
        {job.job_type === 'alpha_prepare' ? (
          <span className="mt-0.5 block text-xs text-muted-foreground/80">
            Pinned above this campaign&apos;s videos
          </span>
        ) : null}
        {pinned ? (
          <span className="mt-0.5 block text-xs text-muted-foreground/80">Pinned while active</span>
        ) : null}
      </TableCell>
      <TableCell>
        <StatusPill status={job.status} />
        <ProgressBar job={job} />
        <FailedJobDetails job={job} />
      </TableCell>
      <TableCell className="text-muted-foreground">{job.output_filename ?? '—'}</TableCell>
      <TableCell className="text-right">
        {canCancel(job) ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => onCancel(job.id)}
          >
            Cancel
          </Button>
        ) : null}
        {job.status === 'failed' ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => onRetry(job.id)}
          >
            Retry
          </Button>
        ) : null}
      </TableCell>
    </TableRow>
  );
}

export function RenderQueueScreen() {
  const { data, isPending, isError } = useQuery(renderQueueQuery);
  const pause = usePauseRenderQueue();
  const resume = useResumeRenderQueue();
  const cancelJob = useCancelRenderJob();
  const retryJob = useRetryRenderJob();
  const reorder = useReorderRenderQueue();
  const [actionError, setActionError] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const busy =
    pause.isPending ||
    resume.isPending ||
    cancelJob.isPending ||
    retryJob.isPending ||
    reorder.isPending;

  const onDragEnd = (event: DragEndEvent) => {
    if (!data) return;
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = data.jobs.findIndex((job) => job.id === active.id);
    const newIndex = data.jobs.findIndex((job) => job.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;

    const next = arrayMove(data.jobs, oldIndex, newIndex);
    setActionError(null);
    reorder.mutate(
      next.map((job) => job.id),
      {
        onError: (error) => setActionError(errorMessage(error)),
      },
    );
  };

  return (
    <div className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight">Render Queue</h1>
        {data && !data.show_resume_prompt ? (
          <div className="flex items-center gap-2">
            {data.paused ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() => {
                  setActionError(null);
                  resume.mutate(undefined, {
                    onError: (error) => setActionError(errorMessage(error)),
                  });
                }}
              >
                <Play data-icon="inline-start" />
                Resume
              </Button>
            ) : (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={busy || data.batch.active_job_count === 0}
                onClick={() => {
                  setActionError(null);
                  pause.mutate(undefined, {
                    onError: (error) => setActionError(errorMessage(error)),
                  });
                }}
              >
                <Pause data-icon="inline-start" />
                Pause
              </Button>
            )}
          </div>
        ) : null}
      </div>

      {data?.show_resume_prompt ? (
        <div className="mt-4">
          <QueueResumeBanner />
        </div>
      ) : null}

      <InlineError message={actionError} className="mt-3 text-sm text-destructive" />

      {isPending ? (
        <div className="mt-6 space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : isError ? (
        <p className="mt-4 text-sm text-muted-foreground">Could not load the render queue.</p>
      ) : data.jobs.length === 0 ? (
        <EmptyState
          icon={ListVideo}
          title="Queue is empty"
          description="Renders queued from a campaign appear here, with progress streamed from the backend."
        />
      ) : (
        <>
          <BatchProgressHeader batch={data.batch} />
          <div className="mt-4 rounded-xl border border-border">
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
              <SortableContext
                items={data.jobs.map((job) => job.id)}
                strategy={verticalListSortingStrategy}
              >
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="w-10" />
                      <TableHead>Campaign</TableHead>
                      <TableHead>Job</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Output</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.jobs.map((job) => (
                      <SortableJobRow
                        key={job.id}
                        job={job}
                        busy={busy}
                        onCancel={(jobId) => {
                          setActionError(null);
                          cancelJob.mutate(jobId, {
                            onError: (error) => setActionError(errorMessage(error)),
                          });
                        }}
                        onRetry={(jobId) => {
                          setActionError(null);
                          retryJob.mutate(jobId, {
                            onError: (error) => setActionError(errorMessage(error)),
                          });
                        }}
                      />
                    ))}
                  </TableBody>
                </Table>
              </SortableContext>
            </DndContext>
          </div>
        </>
      )}
    </div>
  );
}
