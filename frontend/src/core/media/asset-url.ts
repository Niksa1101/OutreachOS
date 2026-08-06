/**
 * ADR-0012: the one place that turns an absolute path the backend vetted into
 * a URL the webview may load.
 *
 * The Tauri asset protocol's static scope (`tauri.conf.json`) is deliberately
 * empty — the workspace root and every source video path are user-chosen at
 * runtime, so there is nothing to name ahead of time. `allow_media_path`
 * grants the Rust-side scope exactly one file before `convertFileSrc` is asked
 * to build a URL for it, mirroring how `dialog:allow-open` already lets the
 * user pick arbitrary files: Rust trusts whatever path the frontend hands it
 * here because that path came back from the authenticated backend, not from
 * unvalidated user input.
 *
 * Grants are per-process and additive, so a path only needs to be granted
 * once; `granted` avoids a redundant `invoke` on every re-render.
 */

import { convertFileSrc, invoke } from '@tauri-apps/api/core';

const granted = new Set<string>();

/** Resolve an absolute file path into a webview-loadable URL. */
export async function mediaSrc(absolutePath: string): Promise<string> {
  if (!granted.has(absolutePath)) {
    await invoke('allow_media_path', { path: absolutePath });
    granted.add(absolutePath);
  }
  return convertFileSrc(absolutePath);
}

/** Test seam: forget every granted path. */
export function forgetGrantedMediaPaths(): void {
  granted.clear();
}
