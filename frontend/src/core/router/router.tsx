/**
 * The route tree.
 *
 * Q18: **code-based**, not file-based. File-based routing would fight the
 * requirement that modules register their own routes — a module is a folder
 * plus one registry line (Q19), and that is not something a directory
 * convention can express.
 *
 * Q48: `/setup` and `/diagnostics` are real routes that sit **outside** the
 * shell layout. They render when the shell cannot, so they must not be
 * children of it.
 */

import { createRootRoute, createRoute, createRouter, redirect } from '@tanstack/react-router';

import { getBootModel } from '@/core/boot/bootStore';
import { RootRoute } from '@/core/layout/RootRoute';
import { ShellLayout } from '@/core/layout/ShellLayout';
import {
  DIAGNOSTICS_PATH,
  HOME_PATH,
  SETUP_PATH,
  isGatePath,
  resolveGate,
} from '@/core/router/guard';
import { DiagnosticsScreen } from '@/core/router/screens/DiagnosticsScreen';
import { HomeScreen } from '@/core/router/screens/HomeScreen';
import { SettingsScreen } from '@/core/router/screens/SettingsScreen';
import { SetupScreen } from '@/core/router/screens/SetupScreen';

/**
 * Where to return to once the app is healthy again (Q78).
 *
 * Module-scoped rather than in the router's own state: it has to survive the
 * redirect *to* `/diagnostics`, which is exactly when router state for the
 * previous route is being torn down.
 */
let rememberedPath = HOME_PATH;

export function rememberPath(pathname: string): void {
  if (!isGatePath(pathname)) {
    rememberedPath = pathname;
  }
}

const rootRoute = createRootRoute({
  beforeLoad: ({ location }) => {
    const { snapshot } = getBootModel();
    rememberPath(location.pathname);

    const target = resolveGate(snapshot.phase, location.pathname, rememberedPath);
    if (target !== null) {
      // `redirect()` returns a control-flow signal, not an `Error`, and
      // throwing it is TanStack Router's documented way to redirect from a
      // loader. The lint rule is right in general and wrong here.
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      throw redirect({ to: target });
    }
  },
  component: RootRoute,
});

const setupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: SETUP_PATH,
  component: SetupScreen,
});

const diagnosticsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: DIAGNOSTICS_PATH,
  component: DiagnosticsScreen,
});

/**
 * The shell layout, as a pathless route. Every real screen is a child, so the
 * sidebar (checkpoint 6) mounts once rather than per route.
 */
const shellRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'shell',
  component: ShellLayout,
});

const homeRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: HOME_PATH,
  component: HomeScreen,
});

/**
 * Q90: read-only in P0. Inside the shell, so it can assume a working database
 * — Q104 routes a degraded backend to `/diagnostics` before this ever mounts,
 * which is why it does not handle 503 itself.
 */
const settingsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: '/settings',
  component: SettingsScreen,
});

const routeTree = rootRoute.addChildren([
  setupRoute,
  diagnosticsRoute,
  shellRoute.addChildren([homeRoute, settingsRoute]),
]);

export const router = createRouter({
  routeTree,
  // The gate decides what renders; a 404 during boot would be a race, not a
  // routing mistake.
  defaultPreload: false,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
