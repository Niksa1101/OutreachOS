/**
 * The boot model, as an external store.
 *
 * It lives outside React because two consumers need it and only one of them is
 * a component: the TanStack Router `beforeLoad` guard (Q48) runs during
 * navigation, where hooks cannot reach. Keeping one store and reading it from
 * both is what stops the guard and the UI from disagreeing about which screen
 * should be on.
 *
 * Q54: `invoke("get_boot_state")` once on mount plus the `boot://state` event
 * stream, both through the same reducer.
 */

import { useSyncExternalStore } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

import {
  bootReducer,
  initialBootModel,
  type BootModel,
  type BootSnapshot,
} from '@/core/boot/bootState';

const BOOT_STATE_EVENT = 'boot://state';

let model: BootModel = initialBootModel;
let started = false;

const listeners = new Set<() => void>();

export function getBootModel(): BootModel {
  return model;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function push(snapshot: BootSnapshot): void {
  const next = bootReducer(model, { type: 'snapshot', snapshot });
  if (next === model) return;

  model = next;
  for (const listener of listeners) listener();
}

/**
 * Attach to Rust. Idempotent — React 19 StrictMode mounts effects twice, and a
 * second listener would double every dispatch.
 */
export async function startBootSubscription(): Promise<void> {
  if (started) return;
  started = true;

  try {
    await listen<BootSnapshot>(BOOT_STATE_EVENT, (event) => push(event.payload));
    push(await invoke<BootSnapshot>('get_boot_state'));
  } catch {
    started = false;
    model = {
      ...model,
      ipcUnavailable: true,
    };
    for (const listener of listeners) listener();
  }
}

export function useBootModel(): BootModel {
  return useSyncExternalStore(subscribe, getBootModel, getBootModel);
}
