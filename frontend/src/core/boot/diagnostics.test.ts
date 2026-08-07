import { describe, expect, it } from 'vitest';

import { presentDiagnostic, UNRECOGNISED } from '@/core/boot/diagnostics';
import type { DiagnosticCode } from '@/core/boot/bootState';

const EXPECTED: Record<
  DiagnosticCode,
  { actions: string[]; log: 'boot' | 'backend'; hasChooseWorkspace: boolean; hasRetry: boolean }
> = {
  workspace_missing: {
    actions: ['retry', 'choose-workspace', 'forget-workspace'],
    log: 'boot',
    hasChooseWorkspace: true,
    hasRetry: true,
  },
  workspace_unwritable: {
    actions: ['choose-workspace', 'retry'],
    log: 'boot',
    hasChooseWorkspace: true,
    hasRetry: true,
  },
  workspace_locked: {
    actions: ['take-over', 'choose-workspace', 'retry'],
    log: 'boot',
    hasChooseWorkspace: true,
    hasRetry: true,
  },
  sidecar_spawn_failed: {
    actions: ['retry'],
    log: 'boot',
    hasChooseWorkspace: false,
    hasRetry: true,
  },
  sidecar_exited: {
    actions: ['retry'],
    log: 'backend',
    hasChooseWorkspace: false,
    hasRetry: true,
  },
  handshake_timeout: {
    actions: ['retry'],
    log: 'backend',
    hasChooseWorkspace: false,
    hasRetry: true,
  },
  port_bind_failed: {
    actions: ['retry'],
    log: 'backend',
    hasChooseWorkspace: false,
    hasRetry: true,
  },
  ffmpeg_missing: {
    actions: ['retry'],
    log: 'backend',
    hasChooseWorkspace: false,
    hasRetry: true,
  },
  ffmpeg_unrunnable: {
    actions: ['retry'],
    log: 'backend',
    hasChooseWorkspace: false,
    hasRetry: true,
  },
  migration_failed: {
    actions: ['retry', 'proceed-without-backup'],
    log: 'backend',
    hasChooseWorkspace: false,
    hasRetry: true,
  },
  database_newer_than_app: {
    actions: ['choose-workspace', 'forget-workspace'],
    log: 'backend',
    hasChooseWorkspace: true,
    hasRetry: false,
  },
  workspace_relocation_failed: {
    actions: ['retry', 'choose-workspace'],
    log: 'boot',
    hasChooseWorkspace: true,
    hasRetry: true,
  },
  unknown: {
    actions: ['retry', 'choose-workspace'],
    log: 'boot',
    hasChooseWorkspace: true,
    hasRetry: true,
  },
};

describe('presentDiagnostic', () => {
  for (const [code, expected] of Object.entries(EXPECTED) as Array<
    [DiagnosticCode, (typeof EXPECTED)[DiagnosticCode]]
  >) {
    it(`defines actions and log for ${code}`, () => {
      const presentation = presentDiagnostic(code);
      expect(presentation.actions).toEqual(expected.actions);
      expect(presentation.log).toBe(expected.log);
      expect(presentation.title.length).toBeGreaterThan(0);
      expect(presentation.explanation.length).toBeGreaterThan(0);

      if (expected.hasChooseWorkspace) {
        expect(presentation.actions).toContain('choose-workspace');
      } else {
        expect(presentation.actions).not.toContain('choose-workspace');
      }

      if (expected.hasRetry) {
        expect(presentation.actions).toContain('retry');
      } else {
        expect(presentation.actions).not.toContain('retry');
      }
    });
  }

  it('falls back to UNRECOGNISED for an unknown wire value', () => {
    // @ts-expect-error — simulates a future code the frontend has not caught up with
    const presentation = presentDiagnostic('future_code');
    expect(presentation).toEqual(UNRECOGNISED);
  });
});
