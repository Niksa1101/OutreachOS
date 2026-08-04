import { describe, expect, it } from 'vitest';

import {
  bootReducer,
  initialBootModel,
  type BootModel,
  type BootSnapshot,
} from '@/core/boot/bootState';

function snapshot(partial: Partial<BootSnapshot> = {}): BootSnapshot {
  return {
    phase: 'starting',
    boot_id: '',
    status: 'Starting…',
    workspace_path: null,
    port: null,
    diagnostic: null,
    ...partial,
  };
}

function apply(model: BootModel, next: BootSnapshot): BootModel {
  return bootReducer(model, { type: 'snapshot', snapshot: next });
}

describe('bootReducer', () => {
  it('replaces the snapshot wholesale rather than merging', () => {
    // Q54: the payload is a full snapshot, not a delta. A reducer that merged
    // would leave a stale diagnostic on screen after a successful retry.
    const failed = apply(
      initialBootModel,
      snapshot({
        phase: 'failed',
        boot_id: 'a',
        diagnostic: { code: 'handshake_timeout', message: 'no port', detail: null },
      }),
    );

    const recovered = apply(failed, snapshot({ phase: 'ready', boot_id: 'b', port: 5000 }));

    expect(recovered.snapshot.diagnostic).toBeNull();
    expect(recovered.snapshot.port).toBe(5000);
  });

  it('opens a session epoch the first time a backend is ready', () => {
    const ready = apply(initialBootModel, snapshot({ phase: 'ready', boot_id: 'a', port: 1 }));
    expect(ready.sessionEpoch).toBe(1);
  });

  it('does not re-open the epoch when the same ready snapshot arrives twice', () => {
    // `get_boot_state` on mount and the first `boot://state` event can deliver
    // the identical snapshot. Clearing the query cache twice on one session
    // would throw away a fetch that had just succeeded.
    const once = apply(initialBootModel, snapshot({ phase: 'ready', boot_id: 'a', port: 1 }));
    const twice = apply(once, snapshot({ phase: 'ready', boot_id: 'a', port: 1 }));

    expect(twice.sessionEpoch).toBe(once.sessionEpoch);
  });

  it('opens a new epoch when Retry produces a different boot_id', () => {
    // Q78: Retry means a new spawn, a new token, and a new boot_id, so the
    // cache from the previous process must not be reused.
    const first = apply(initialBootModel, snapshot({ phase: 'ready', boot_id: 'a', port: 1 }));
    const failed = apply(first, snapshot({ phase: 'failed', boot_id: 'a' }));
    const second = apply(failed, snapshot({ phase: 'ready', boot_id: 'b', port: 2 }));

    expect(second.sessionEpoch).toBe(2);
  });

  it('does not open an epoch for a failure or for an in-progress boot', () => {
    let model = apply(initialBootModel, snapshot({ phase: 'starting_backend', boot_id: 'a' }));
    expect(model.sessionEpoch).toBe(0);

    model = apply(
      model,
      snapshot({
        phase: 'failed',
        boot_id: 'a',
        diagnostic: { code: 'sidecar_exited', message: 'gone', detail: null },
      }),
    );
    expect(model.sessionEpoch).toBe(0);
  });

  it('ignores a ready phase that carries no boot_id', () => {
    // Defensive: a ready state without an identity cannot be keyed on, and
    // treating it as a new session would clear the cache on every delivery.
    const model = apply(initialBootModel, snapshot({ phase: 'ready', boot_id: '' }));
    expect(model.sessionEpoch).toBe(0);
  });

  it('re-opens the epoch when the same boot_id returns after an intervening one', () => {
    // boot_ids are UUIDs so this is vanishingly unlikely, but the rule should
    // be "different from the last ready one", not "never seen before" — the
    // latter needs unbounded memory to enforce.
    let model = apply(initialBootModel, snapshot({ phase: 'ready', boot_id: 'a', port: 1 }));
    model = apply(model, snapshot({ phase: 'ready', boot_id: 'b', port: 2 }));
    model = apply(model, snapshot({ phase: 'ready', boot_id: 'a', port: 3 }));

    expect(model.sessionEpoch).toBe(3);
  });
});
