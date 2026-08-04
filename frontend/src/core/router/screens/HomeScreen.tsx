/**
 * The landing screen.
 *
 * Honest empty state, like every other P0 page. The heartbeat that proves the
 * SSE path works lives in the shell header (`ConnectionBadge`) rather than
 * here — it is a property of the connection, not of this screen, and it should
 * stay visible when the user navigates away.
 */

import { Link } from '@tanstack/react-router';
import { Clapperboard } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { EmptyState } from '@/core/ui/EmptyState';

export function HomeScreen() {
  return (
    <div className="p-6">
      <EmptyState
        icon={Clapperboard}
        title="OutreachOS"
        description="A modular workspace for outbound sales. V1 ships one module: Video Composer, which composites a talking-head recording over a batch of screen recordings."
        // `render`, not `asChild` — Base UI's composition API.
        action={
          <Button render={<Link to="/video-composer/campaigns" />} variant="outline" size="sm">
            Open Video Composer
          </Button>
        }
      />
    </div>
  );
}
