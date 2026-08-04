import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { BootErrorBoundary } from '@/core/boot/BootErrorBoundary';
import { installClientErrorReporting } from '@/core/boot/clientErrors';
import { AppRoot } from '@/core/layout/AppRoot';

// Installed before the first render, so an error thrown during mount is
// captured rather than lost to the console of a window that is not visible yet.
installClientErrorReporting();

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
