/**
 * Subscribe to Rust's boot state machine.
 *
 * Q54: one `invoke("get_boot_state")` on mount plus the `boot://state` event
 * stream, both feeding the same reducer. The listener is attached *before* the
 * initial fetch so a transition that lands between the two is not lost.
 */

import { useEffect, useReducer, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

import {
  bootReducer,
  initialBootModel,
  type BootModel,
  type BootSnapshot,
} from '@/core/boot/bootState';

const BOOT_STATE_EVENT = 'boot://state';

export function useBootState(): BootModel {
  const [model, dispatch] = useReducer(bootReducer, initialBootModel);
  const [, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    let unlisten: UnlistenFn | undefined;

    void (async () => {
      try {
        // Listener first. Between `get_boot_state` returning and a listener
        // being attached there is a window in which a transition would be
        // dropped, and on a fast handshake that window contains `ready`.
        unlisten = await listen<BootSnapshot>(BOOT_STATE_EVENT, (event) => {
          if (!cancelled) dispatch({ type: 'snapshot', snapshot: event.payload });
        });

        const initial = await invoke<BootSnapshot>('get_boot_state');
        if (!cancelled) dispatch({ type: 'snapshot', snapshot: initial });
      } catch (cause) {
        // Outside a Tauri webview there is no IPC bridge. Surfacing through
        // state rather than throwing keeps this out of the error boundary,
        // which would otherwise make `vite dev` in a browser unusable.
        if (!cancelled) setError(cause);
      }
    })();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  return model;
}
