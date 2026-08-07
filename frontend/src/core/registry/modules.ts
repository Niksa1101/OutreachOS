/**
 * The module registry.
 *
 * Q19: `ModuleDefinition { id, label, icon, navItems[], routes[] }` in a static
 * array. **Adding a module is a folder plus one line here.**
 *
 * The array is static rather than discovered, deliberately. Dynamic discovery
 * would mean the route tree is not knowable at build time, which costs
 * TanStack Router's type safety — the exact thing Tech.md §8 chose it over
 * React Router for.
 *
 * Q20 is the other half: `eslint-plugin-boundaries` forbids cross-module
 * imports, so this file is the only place a module's existence is visible to
 * anything outside it.
 */

import type { LucideIcon } from 'lucide-react';
import { Clapperboard, LayoutList, ListVideo } from 'lucide-react';

export interface NavItem {
  /** The route path. Must match a route the module registers. */
  to: string;
  label: string;
  icon: LucideIcon;
  /**
   * Ticket 18: when set, the sidebar shows a live count badge driven by the
   * global render-queue query. Core knows how to resolve the kind; modules only
   * opt in — they cannot push a React node across the boundary.
   */
  badge?: 'render-queue-active';
}

export interface ModuleDefinition {
  id: string;
  label: string;
  icon: LucideIcon;
  navItems: NavItem[];
}

/**
 * V1 ships one module (PRD §1). CRM, Lead Finder, Outreach and Analytics are
 * each a folder under `modules/` and a line in this array.
 *
 * The routes themselves are registered in `core/router/router.tsx` — the
 * registry describes *navigation*, and keeping the two apart means a module can
 * own a route that has no nav entry (a detail page) without inventing a flag
 * for it.
 */
export const MODULES: readonly ModuleDefinition[] = [
  {
    id: 'video-composer',
    label: 'Video Composer',
    icon: Clapperboard,
    navItems: [
      { to: '/video-composer/campaigns', label: 'Campaigns', icon: LayoutList },
      {
        to: '/video-composer/queue',
        label: 'Render Queue',
        icon: ListVideo,
        badge: 'render-queue-active',
      },
    ],
  },
];
