import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { AppRoot } from '@/core/layout/AppRoot';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root is missing from index.html');
}

createRoot(container).render(
  <StrictMode>
    <AppRoot />
  </StrictMode>,
);
