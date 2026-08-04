/**
 * The boot reducer.
 *
 * Q54: Rust owns the state machine and emits **full snapshots**, so this is one
 * reducer over one shape — `invoke("get_boot_state")` on mount and the
 * `boot://state` event thereafter deserialise into the same type.
 *
 * The reducer is not a pass-through. It derives `sessionEpoch`, which is the
 * answer to Q78's requirement that a successful Retry clear the query cache:
 * Retry mints a new `boot_id`, and a cache populated by a process that no
 * longer exists is worse than an empty one.
 */

/**
 * Mirrors `BootPhase` in `src-tauri/src/boot.rs`.
 *
 * `phases_serialise_to_the_snake_case_the_reducer_matches_on` over there
 * asserts the wire values, so a rename on the Rust side fails a test rather
 * than silently dropping this union into its `default` branch.
 */
export type BootPhase =
  | 'starting'
  /** Q13: no workspace pointer, and therefore **no sidecar**. */
  | 'awaiting_workspace'
  | 'starting_backend'
  | 'ready'
  | 'failed';

/** Mirrors `DiagnosticCode` in `src-tauri/src/diagnostics.rs`. */
export type DiagnosticCode =
  | 'workspace_missing'
  | 'workspace_unwritable'
  | 'workspace_locked'
  | 'sidecar_spawn_failed'
  | 'sidecar_exited'
  | 'handshake_timeout'
  | 'migration_failed'
  | 'database_newer_than_app'
  | 'unknown';

export interface Diagnostic {
  code: DiagnosticCode;
  message: string;
  detail: string | null;
}

/** Mirrors `BootState` in `src-tauri/src/boot.rs`. Carries no token, by design. */
export interface BootSnapshot {
  phase: BootPhase;
  boot_id: string;
  status: string;
  workspace_path: string | null;
  port: number | null;
  diagnostic: Diagnostic | null;
}

export interface BootModel {
  snapshot: BootSnapshot;
  /**
   * Increments each time a **ready** backend appears under a `boot_id` this
   * model has not seen ready before.
   *
   * Consumers key their cache reset off this rather than off `boot_id`
   * directly, so a failed attempt between two ready states does not trigger a
   * spurious clear, and a re-delivered snapshot does not either.
   */
  sessionEpoch: number;
  /** True when Tauri IPC is unavailable (plain browser tab). */
  ipcUnavailable: boolean;
}

export type BootAction = { type: 'snapshot'; snapshot: BootSnapshot };

export const initialBootModel: BootModel = {
  snapshot: {
    phase: 'starting',
    boot_id: '',
    status: 'Starting…',
    workspace_path: null,
    port: null,
    diagnostic: null,
  },
  sessionEpoch: 0,
  ipcUnavailable: false,
};

export function bootReducer(model: BootModel, action: BootAction): BootModel {
  const next = action.snapshot;
  const previous = model.snapshot;

  const becameReadyUnderANewBootId =
    next.phase === 'ready' &&
    next.boot_id !== '' &&
    !(previous.phase === 'ready' && previous.boot_id === next.boot_id);

  return {
    snapshot: next,
    sessionEpoch: becameReadyUnderANewBootId ? model.sessionEpoch + 1 : model.sessionEpoch,
    ipcUnavailable: model.ipcUnavailable,
  };
}
