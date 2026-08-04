/**
 * Render Queue — an honest empty state.
 *
 * P4 builds this. The queue table, its drag reordering, and the progress
 * events that drive it all arrive together, because a queue you cannot reorder
 * or watch is not a queue.
 */

import { ListVideo } from 'lucide-react';

import { EmptyState } from '@/core/ui/EmptyState';

export function RenderQueueScreen() {
  return (
    <div className="p-6">
      <h1 className="text-lg font-semibold tracking-tight">Render Queue</h1>
      <EmptyState
        icon={ListVideo}
        title="Queue is empty"
        description="Renders queued from a campaign appear here, with progress streamed from the backend. Rendering arrives in a later phase."
      />
    </div>
  );
}
