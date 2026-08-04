import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Relative, not aliased: the `@/` paths are scoped to `core/` and `modules/`
// so the boundary lint has something precise to police, and the stylesheet
// entry sits above both.
import './index.css';

import { BootErrorBoundary } from '@/core/boot/BootErrorBoundary';
import { startBootSubscription } from '@/core/boot/bootStore';
import { installClientErrorReporting } from '@/core/boot/clientErrors';
import { AppRoot } from '@/core/layout/AppRoot';

// Installed before the first render, so an error thrown during mount is
// captured rather than lost to the console of a window that is not visible yet.
installClientErrorReporting();

// Started before the first render too, but deliberately not awaited: the boot
// screen must paint so `app_ready` can fire and the window can appear. Awaiting
// here would hold the window hidden until Rust answered, which is the failure
// the 3s watchdog exists to bound.
void startBootSubscription();

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root is missing from index.html');
}

createRoot(container).render(
  <StrictMode>
    <BootErrorBoundary>
      <AppRoot />
    </BootErrorBoundary>
  </StrictMode>,
);
