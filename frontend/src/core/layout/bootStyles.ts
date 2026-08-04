/**
 * Inline styles for the pre-token surfaces.
 *
 * Design tokens arrive in checkpoint 6, and Tech.md §3.3 makes hardcoded
 * colours and spacing a review failure. These are the deliberate exception:
 * the boot screen, the picker, the diagnostics screen, and the error boundary
 * all have to render correctly when the failure *is* the stylesheet, so they
 * cannot depend on one.
 *
 * **Checkpoint 6 deletes this file** and moves these four surfaces onto tokens,
 * with the error boundary keeping a minimal inline fallback.
 */

import type { CSSProperties } from 'react';

/** zinc-950 / zinc-50, the values `--color-bg` and `--color-fg` will take. */
export const BACKGROUND = '#09090b';
export const FOREGROUND = '#fafafa';
export const BORDER = '#27272a';
/** oklch(0.58 0.15 255) in sRGB — the accent from ADR-0001. */
export const ACCENT = '#337bd0';

export const bootSurface: CSSProperties = {
  display: 'grid',
  placeContent: 'center',
  minHeight: '100vh',
  gap: '0.75rem',
  textAlign: 'center',
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
  color: FOREGROUND,
  background: BACKGROUND,
  padding: '2rem',
};

/** A left-aligned surface for screens with more than two lines on them. */
export const paneSurface: CSSProperties = {
  minHeight: '100vh',
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
  color: FOREGROUND,
  background: BACKGROUND,
  padding: '3rem 2rem',
};

export const pane: CSSProperties = {
  maxWidth: '52rem',
  margin: '0 auto',
  display: 'grid',
  gap: '1.25rem',
};

export const mono: CSSProperties = {
  fontFamily: 'ui-monospace, "Cascadia Mono", Consolas, monospace',
  fontSize: '0.8125rem',
};

export const logTail: CSSProperties = {
  ...mono,
  background: '#0f0f11',
  border: `1px solid ${BORDER}`,
  borderRadius: '0.5rem',
  padding: '0.75rem',
  maxHeight: '18rem',
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  margin: 0,
};

export function button(variant: 'primary' | 'secondary' = 'secondary'): CSSProperties {
  return {
    font: 'inherit',
    fontSize: '0.875rem',
    padding: '0.5rem 0.875rem',
    borderRadius: '0.5rem',
    cursor: 'pointer',
    border: `1px solid ${variant === 'primary' ? ACCENT : BORDER}`,
    background: variant === 'primary' ? ACCENT : 'transparent',
    color: FOREGROUND,
  };
}
