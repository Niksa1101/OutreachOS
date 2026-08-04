/**
 * Campaigns — an honest empty state.
 *
 * P2 builds this screen. P0 renders what is true right now: there are no
 * campaigns, and there is no way to make one yet. The alternative — a table of
 * invented rows — makes the application look further along than it is, and
 * every screenshot taken of it becomes a small lie.
 */

import { LayoutList } from 'lucide-react';

import { EmptyState } from '@/core/ui/EmptyState';

export function CampaignsScreen() {
  return (
    <div className="p-6">
      <h1 className="text-lg font-semibold tracking-tight">Campaigns</h1>
      <EmptyState
        icon={LayoutList}
        title="No campaigns yet"
        description="A campaign holds one talking-head recording and the screen recordings it is composited onto. Creating them arrives in a later phase."
      />
    </div>
  );
}
