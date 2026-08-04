/**
 * The diagnostics screen.
 *
 * **Everything here is DB-free by construction** (Q104). This screen renders
 * precisely when the database may be unusable, so nothing on it may touch a DB
 * route — otherwise it fails exactly when it is needed. Its two sources are
 * Rust `invoke`s and the boot state, and that is the whole list.
 *
 * Q87 is the same argument one level down: the log tail is read Rust-side,
 * because an API-based log read fails at the same moment for the same reason.
 * `read_log_tail` takes a `"boot" | "backend"` discriminant and never a path,
 * so traversal is impossible by construction rather than prevented by
 * validation.
 */

import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { writeText } from '@tauri-apps/plugin-clipboard-manager';
import { open } from '@tauri-apps/plugin-dialog';

import { useBootModel } from '@/core/boot/bootStore';
import { presentDiagnostic, type DiagnosticAction } from '@/core/boot/diagnostics';
import { BORDER, button, logTail, mono, pane, paneSurface } from '@/core/layout/bootStyles';

export function DiagnosticsScreen() {
  const { snapshot } = useBootModel();
  const diagnostic = snapshot.diagnostic;
  const presentation = presentDiagnostic(diagnostic?.code ?? 'unknown');

  const [tail, setTail] = useState('Loading…');
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void invoke<string>('read_log_tail', { which: presentation.log })
      .then((contents) => {
        if (!cancelled) setTail(contents.trim() || '(the log is empty)');
      })
      .catch((cause: unknown) => {
        if (!cancelled) setTail(`Could not read the log: ${String(cause)}`);
      });

    return () => {
      cancelled = true;
    };
  }, [presentation.log, snapshot.boot_id]);

  async function run(action: DiagnosticAction) {
    setBusy(true);
    try {
      switch (action) {
        case 'retry':
          // Q78: this re-runs the whole boot machine — new spawn, new token,
          // new boot_id. The cache clear on success is handled where the
          // session epoch changes, not here.
          await invoke('retry_boot');
          break;
        case 'forget-workspace':
          await invoke('forget_workspace');
          break;
        case 'choose-workspace': {
          const selected = await open({
            directory: true,
            multiple: false,
            title: 'Choose a workspace',
          });
          if (typeof selected === 'string') {
            await invoke('set_workspace', { path: selected });
          }
          break;
        }
        case 'take-over':
          await invoke('take_over_workspace');
          break;
        case 'proceed-without-backup':
          await invoke('proceed_without_backup');
          break;
      }
    } finally {
      setBusy(false);
    }
  }

  async function copyAll() {
    // Q103: the plugin rather than `navigator.clipboard`. The latter almost
    // certainly works, but this is the one button that only ever renders when
    // the user is already stuck — a dead one here would be found by a user
    // rather than by us.
    await writeText(
      [
        `code: ${diagnostic?.code ?? 'unknown'}`,
        `boot_id: ${snapshot.boot_id}`,
        `workspace: ${snapshot.workspace_path ?? '(none)'}`,
        '',
        diagnostic?.message ?? '',
        diagnostic?.detail ?? '',
        '',
        `--- ${presentation.log} log ---`,
        tail,
      ].join('\n'),
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <main style={paneSurface}>
      <div style={pane}>
        <header style={{ display: 'grid', gap: '0.5rem' }}>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0 }}>{presentation.title}</h1>
          <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9375rem', lineHeight: 1.6 }}>
            {presentation.explanation}
          </p>
        </header>

        <dl
          style={{
            ...mono,
            display: 'grid',
            gridTemplateColumns: 'max-content 1fr',
            gap: '0.25rem 1.5rem',
            margin: 0,
            opacity: 0.7,
          }}
        >
          <dt>code</dt>
          <dd style={{ margin: 0 }}>{diagnostic?.code ?? 'unknown'}</dd>
          <dt>workspace</dt>
          <dd style={{ margin: 0, wordBreak: 'break-all' }}>
            {snapshot.workspace_path ?? '(none selected)'}
          </dd>
          <dt>boot_id</dt>
          <dd style={{ margin: 0 }}>{snapshot.boot_id || '—'}</dd>
        </dl>

        {diagnostic?.detail ? <pre style={logTail}>{diagnostic.detail}</pre> : null}

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {presentation.actions.map((action, index) => (
            <button
              key={action}
              type="button"
              style={button(index === 0 ? 'primary' : 'secondary')}
              disabled={busy}
              onClick={() => void run(action)}
            >
              {ACTION_LABELS[action]}
            </button>
          ))}
        </div>

        <section
          style={{
            display: 'grid',
            gap: '0.5rem',
            borderTop: `1px solid ${BORDER}`,
            paddingTop: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <h2 style={{ fontSize: '0.875rem', fontWeight: 600, margin: 0, flex: 1 }}>
              {presentation.log === 'boot' ? 'Startup log' : 'Backend log'}
            </h2>
            <button type="button" style={button()} onClick={() => void copyAll()}>
              {copied ? 'Copied' : 'Copy to clipboard'}
            </button>
            <button
              type="button"
              style={button()}
              onClick={() => void invoke('open_logs_folder', { which: presentation.log })}
            >
              Open logs folder
            </button>
          </div>
          <pre style={logTail}>{tail}</pre>
        </section>
      </div>
    </main>
  );
}

const ACTION_LABELS: Record<DiagnosticAction, string> = {
  retry: 'Retry',
  'choose-workspace': 'Choose Workspace',
  'forget-workspace': 'Forget this workspace',
  'take-over': 'Take over',
  'proceed-without-backup': 'Proceed without backup',
};
