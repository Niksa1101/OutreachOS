/**
 * The application sidebar.
 *
 * Q47: shadcn's `Sidebar`, collapsible to an icon rail, sections driven by the
 * module registry, `Settings` pinned at the bottom, collapse state in
 * localStorage.
 *
 * Nothing here knows what Video Composer is. It renders whatever
 * `MODULES` contains, which is what makes Q19's promise — a module is a folder
 * plus one registry line — true rather than aspirational.
 */

import { Link, useRouterState } from '@tanstack/react-router';
import { Settings } from 'lucide-react';

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/core/components/ui/sidebar';
import { useRenderQueueActiveCount } from '@/core/hooks/useRenderQueueActiveCount';
import { MODULES } from '@/core/registry/modules';

function RenderQueueActiveBadge() {
  const activeCount = useRenderQueueActiveCount();
  if (activeCount <= 0) {
    return null;
  }

  return (
    <SidebarMenuBadge className="bg-primary text-primary-foreground">
      {activeCount > 99 ? '99+' : activeCount}
    </SidebarMenuBadge>
  );
}

export function AppSidebar() {
  // `useRouterState` rather than `useMatchRoute`: the active check is a plain
  // prefix comparison, and subscribing to the location is cheaper than
  // matching every nav item against the route tree on each render.
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          {/* The wordmark, not a logo. Tech.md §2 calls the icon a placeholder;
              putting it here would give a placeholder permanent prominence. */}
          <span className="truncate text-sm font-semibold tracking-tight group-data-[collapsible=icon]:hidden">
            OutreachOS
          </span>
        </div>
      </SidebarHeader>

      <SidebarContent>
        {MODULES.map((module) => (
          <SidebarGroup key={module.id}>
            <SidebarGroupLabel>{module.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {module.navItems.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    {/* `render`, not `asChild`: this preset's primitives are
                        Base UI. The nav row has to *be* an anchor — a button
                        with an onClick would break middle-click, the keyboard
                        contract, and the router's own prefetch hooks. */}
                    <SidebarMenuButton
                      render={<Link to={item.to} />}
                      isActive={pathname.startsWith(item.to)}
                      tooltip={item.label}
                    >
                      <item.icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                    {item.badge === 'render-queue-active' ? <RenderQueueActiveBadge /> : null}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      {/* Q47: pinned bottom. Settings is not a module — it is the application's
          own, and grouping it with one would imply it belongs to that module. */}
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              render={<Link to="/settings" />}
              isActive={pathname === '/settings'}
              tooltip="Settings"
            >
              <Settings />
              <span>Settings</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
