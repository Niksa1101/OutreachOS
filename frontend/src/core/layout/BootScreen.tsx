/**
 * Q102: a wordmark and one status line.
 *
 * No spinner before 400ms, and no artificial minimum — a boot that finishes in
 * 200ms should look instant rather than being held back to make the spinner
 * worth showing.
 *
 * The 400ms delay is a `setTimeout` here rather than a CSS animation delay
 * because checkpoint 6's `--motion-*` tokens zero out under
 * `prefers-reduced-motion`, and this delay is about perceived latency, not
 * motion. Zeroing it would make the spinner flash on every fast boot for
 * exactly the users least likely to want that.
 */

import { useEffect, useState } from 'react';

import { useBootModel } from '@/core/boot/bootStore';
import { bootSurface, mono } from '@/core/layout/bootStyles';

const SPINNER_DELAY_MS = 400;

export function BootScreen({ status }: { status: string }) {
  const { ipcUnavailable } = useBootModel();
  const [showActivity, setShowActivity] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowActivity(true), SPINNER_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <main style={bootSurface}>
      <h1 style={{ fontSize: '1.125rem', fontWeight: 600, letterSpacing: '-0.01em', margin: 0 }}>
        OutreachOS
      </h1>
      <p style={{ margin: 0, fontSize: '0.875rem', opacity: showActivity ? 0.6 : 0 }}>{status}</p>
      {ipcUnavailable ? (
        <p style={{ margin: 0, fontSize: '0.875rem', opacity: 0.75, maxWidth: '28rem' }}>
          Run inside the Tauri app (<code style={mono}>pnpm dev</code>), not a browser tab.
        </p>
      ) : null}
      <span style={{ ...mono, opacity: 0 }} aria-hidden>
        {/* Reserves the status line's height so the layout does not shift when
            the text appears. */}
        &nbsp;
      </span>
    </main>
  );
}
