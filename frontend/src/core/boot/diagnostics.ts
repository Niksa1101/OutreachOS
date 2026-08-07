/**
 * What each diagnostics code means to a user, and what they can do about it.
 *
 * Q124 fixes the nine original codes; ticket 29 adds `port_bind_failed`,
 * `ffmpeg_missing`, and `ffmpeg_unrunnable`. This is the presentation layer over them. The
 * action set is the reason `workspace_locked` was not merged into
 * `workspace_unwritable`: they need different buttons, and a merge would either
 * offer "Take over" on a permissions failure or hide it on a lock.
 *
 * `src-tauri/src/diagnostics.rs` has a test asserting the wire values match the
 * union in `bootState.ts`. This file is the other half — a code that arrives
 * without an entry here falls through to `UNRECOGNISED`, which is still a
 * usable screen rather than a blank one.
 */

import type { DiagnosticCode } from '@/core/boot/bootState';

export type DiagnosticAction =
  'retry' | 'choose-workspace' | 'forget-workspace' | 'take-over' | 'proceed-without-backup';

export interface DiagnosticPresentation {
  title: string;
  /** One paragraph. What happened, in the user's terms. */
  explanation: string;
  actions: DiagnosticAction[];
  /** Which log is likely to contain the cause. */
  log: 'boot' | 'backend';
}

export const UNRECOGNISED: DiagnosticPresentation = {
  title: 'Something stopped OutreachOS from starting',
  explanation:
    'The details below were written to the log. This is a failure the app does not have a specific explanation for.',
  actions: ['retry', 'choose-workspace'],
  log: 'boot',
};

const PRESENTATIONS: Record<DiagnosticCode, DiagnosticPresentation> = {
  workspace_missing: {
    title: 'The workspace folder is missing',
    explanation:
      'The folder OutreachOS was using is no longer where it was. It may have been renamed or moved, or it may be on a drive that is not connected.',
    // Q40: "Forget this workspace" is what stops this being a permanent boot
    // loop whose only exit is editing app-data by hand.
    actions: ['retry', 'choose-workspace', 'forget-workspace'],
    log: 'boot',
  },
  workspace_unwritable: {
    title: 'The workspace folder cannot be written to',
    explanation:
      'OutreachOS could not create a file in the workspace. This usually means the folder belongs to another user, or is inside a protected location such as Program Files.',
    actions: ['choose-workspace', 'retry'],
    log: 'boot',
  },
  workspace_locked: {
    title: 'The workspace is in use',
    explanation:
      'Another copy of OutreachOS appears to have this workspace open. If that copy is not running any more — for example, after a crash or on another machine — you can take it over.',
    actions: ['take-over', 'choose-workspace', 'retry'],
    log: 'boot',
  },
  sidecar_spawn_failed: {
    title: 'The backend could not be started',
    explanation:
      'OutreachOS could not launch its backend process at all. The log below records where it looked for it.',
    actions: ['retry'],
    log: 'boot',
  },
  sidecar_exited: {
    title: 'The backend stopped',
    explanation:
      'The backend process ended unexpectedly. Retrying starts a fresh one; nothing in the workspace has been changed.',
    actions: ['retry'],
    log: 'backend',
  },
  handshake_timeout: {
    title: 'The backend did not finish starting',
    explanation:
      'The backend was launched but did not become ready in time. The details below say how far it got.',
    actions: ['retry'],
    log: 'backend',
  },
  port_bind_failed: {
    title: 'The backend could not bind a local port',
    explanation:
      'OutreachOS could not open a loopback network port for its backend. Another program may be interfering, or the system may be out of available ports.',
    actions: ['retry'],
    log: 'backend',
  },
  ffmpeg_missing: {
    title: 'The bundled video tools are missing',
    explanation:
      'OutreachOS could not find FFmpeg or FFprobe where the installer placed them. Reinstalling the application may restore them.',
    actions: ['retry'],
    log: 'backend',
  },
  ffmpeg_unrunnable: {
    title: 'The bundled video tools could not be run',
    explanation:
      'FFmpeg or FFprobe is present but failed to start. The log below may show an antivirus block, a permissions problem, or corrupted binaries.',
    actions: ['retry'],
    log: 'backend',
  },
  migration_failed: {
    title: 'The database could not be updated',
    explanation:
      'OutreachOS could not apply a required database change. Your data has not been modified — the update was stopped before it began.',
    actions: ['retry', 'proceed-without-backup'],
    log: 'backend',
  },
  database_newer_than_app: {
    title: 'This workspace was made by a newer version',
    explanation:
      'The database in this workspace uses a newer format than this copy of OutreachOS understands. Opening it anyway could damage it, so it has not been opened. Install the newer version, or choose a different workspace.',
    // Deliberately no Retry: retrying does the same thing and fails the same
    // way. Offering it would suggest the problem might resolve itself.
    actions: ['choose-workspace', 'forget-workspace'],
    log: 'backend',
  },
  workspace_relocation_failed: {
    title: 'The workspace could not be moved',
    explanation:
      'OutreachOS stopped the backend and tried to switch workspace locations, but the move did not finish. Your original workspace is still the active one — nothing was pointed at the new folder.',
    actions: ['retry', 'choose-workspace'],
    log: 'boot',
  },
  unknown: UNRECOGNISED,
};

export function presentDiagnostic(code: DiagnosticCode): DiagnosticPresentation {
  return PRESENTATIONS[code] ?? UNRECOGNISED;
}
