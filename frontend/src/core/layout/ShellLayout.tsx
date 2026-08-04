/**
 * The application shell.
 *
 * Q104: this mounts only in the ready phase. Rust fails boot when `/health`
 * reports `status: degraded`, so the shell assumes a working database rather
 * than each screen handling 503.
 *
 * Q66: the single SSE connection is owned here, inside the ready state,
 * because before that there is no port and no token to connect with.
 */

import { Outlet } from '@tanstack/react-router';

import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/core/components/ui/sidebar';
import { TooltipProvider } from '@/core/components/ui/tooltip';
import { useBootModel } from '@/core/boot/bootStore';
import { AppSidebar } from '@/core/layout/AppSidebar';
import { ConnectionBadge } from '@/core/layout/ConnectionBadge';
import { EventStreamProvider } from '@/core/sse/EventStreamProvider';

export function ShellLayout() {
  const { sessionEpoch } = useBootModel();

  return (
    <EventStreamProvider sessionEpoch={sessionEpoch}>
      {/* Q47: collapse state in localStorage. shadcn's provider persists it to
          a cookie by default, which a local application has no use for — the
          `storageKey`-less API means this is the supported seam. */}
      {/* `delay`, not `delayDuration`: this preset's primitives are Base UI,
          not Radix. The composition API differs too — `render={<X/>}` where
          Radix has `asChild`. */}
      <TooltipProvider delay={300}>
        <SidebarProvider>
          <AppSidebar />
          <SidebarInset>
            <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
              <SidebarTrigger />
              <div className="flex-1" />
              <ConnectionBadge />
            </header>
            <div className="flex-1 overflow-auto">
              <Outlet />
            </div>
          </SidebarInset>
        </SidebarProvider>
      </TooltipProvider>
    </EventStreamProvider>
  );
}
