/**
 * The workspace picker.
 *
 * Q13: this screen runs when there is **no backend at all**, so every check it
 * makes is a Rust `invoke`. That is the invariant, not an optimisation — the
 * sidecar is not spawned until a workspace exists.
 *
 * Q14: the blocking rules are deliberately few. A detected sync or network
 * path is a dismissible warning with "choose anyway", because hard-refusing
 * OneDrive would misfire constantly — Windows 11 puts `Documents` under
 * OneDrive by default.
 */

import { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';

import { BORDER, button, mono, pane, paneSurface } from '@/core/layout/bootStyles';

interface WorkspaceWarning {
  kind: 'network_drive' | 'unc_path' | 'cloud_sync' | 'path_length';
  provider?: string;
  length?: number;
}

type WorkspaceRejection =
  | 'not_found'
  | 'not_a_directory'
  | 'not_writable'
  | 'not_empty'
  | 'corrupt_database'
  | 'drive_root'
  | 'install_directory'
  | 'app_data_directory'
  | 'path_too_long';

interface WorkspaceValidation {
  path: string;
  rejection: WorkspaceRejection | null;
  warnings: WorkspaceWarning[];
  existing: boolean;
}

/** Q117 and Q14, in the user's terms. Each says *why*, not just "no". */
const REJECTION_TEXT: Record<WorkspaceRejection, string> = {
  not_found: 'That folder no longer exists.',
  not_a_directory: 'That is a file, not a folder.',
  not_writable:
    'OutreachOS cannot write there. Protected locations such as Program Files need administrator rights, which this app deliberately never asks for.',
  not_empty:
    'That folder already contains other files. Pick an empty folder, or one that already holds an OutreachOS workspace — this is what stops a workspace being created on top of your Desktop or Documents.',
  corrupt_database:
    'That folder contains an outreachos.db that is not a database file. Opening it could destroy whatever it actually is.',
  drive_root: 'A whole drive cannot be a workspace. Pick a folder on it instead.',
  install_directory:
    'That is where OutreachOS itself is installed. Data there would be lost on the next update.',
  app_data_directory:
    'That folder holds the pointer to your workspace, so it cannot also be the workspace.',
  path_too_long:
    'That path is too long. OutreachOS writes cache files several levels below the workspace, and Windows would refuse to create them.',
};

function warningText(warning: WorkspaceWarning): string {
  switch (warning.kind) {
    case 'cloud_sync':
      return `This folder is inside ${warning.provider ?? 'a cloud-sync folder'}. The sync client can rewrite files while OutreachOS has the database open, which can corrupt it. Renders are large, and syncing them will be slow.`;
    case 'network_drive':
      return 'This folder is on a network drive. SQLite file locking over a network share is unreliable.';
    case 'unc_path':
      return 'This is a network path. SQLite file locking over a network share is unreliable.';
    case 'path_length':
      return `This path is ${warning.length ?? 0} characters. OutreachOS writes files several levels below it, and long paths can hit the Windows limit.`;
  }
}

export function SetupScreen() {
  const [candidate, setCandidate] = useState<WorkspaceValidation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function choose() {
    setError(null);
    const selected = await open({ directory: true, multiple: false, title: 'Choose a workspace' });
    if (typeof selected !== 'string') return;

    setBusy(true);
    try {
      setCandidate(await invoke<WorkspaceValidation>('validate_workspace', { path: selected }));
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!candidate || candidate.rejection) return;

    setBusy(true);
    setError(null);
    try {
      // Rust re-validates before storing. The picker's own validation is for
      // *showing* the user what is wrong; it is not the thing being trusted.
      const result = await invoke<WorkspaceValidation>('set_workspace', {
        path: candidate.path,
      });
      if (result.rejection) {
        setCandidate(result);
      }
      // On success the boot machine restarts and the gate routes away from
      // here. There is nothing to navigate to explicitly.
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={paneSurface}>
      <div style={pane}>
        <header style={{ display: 'grid', gap: '0.5rem' }}>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0 }}>Choose a workspace</h1>
          <p style={{ margin: 0, opacity: 0.7, fontSize: '0.9375rem', lineHeight: 1.6 }}>
            OutreachOS keeps everything for a project in one folder — its database, cached clips,
            rendered videos, and logs. Pick an empty folder, or one you have used before. You can
            move it later by moving the whole folder.
          </p>
        </header>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            type="button"
            style={button('primary')}
            onClick={() => void choose()}
            disabled={busy}
          >
            Choose folder…
          </button>
        </div>

        {error ? (
          <p style={{ ...mono, color: '#f87171', margin: 0 }} role="alert">
            {error}
          </p>
        ) : null}

        {candidate ? (
          <section
            style={{
              border: `1px solid ${BORDER}`,
              borderRadius: '0.5rem',
              padding: '1rem',
              display: 'grid',
              gap: '0.75rem',
            }}
          >
            <p style={{ ...mono, margin: 0, opacity: 0.8, wordBreak: 'break-all' }}>
              {candidate.path}
            </p>

            {candidate.rejection ? (
              <p style={{ margin: 0, color: '#f87171', fontSize: '0.875rem', lineHeight: 1.6 }}>
                {REJECTION_TEXT[candidate.rejection]}
              </p>
            ) : (
              <>
                <p style={{ margin: 0, fontSize: '0.875rem', opacity: 0.8 }}>
                  {candidate.existing
                    ? 'This folder already holds an OutreachOS workspace. It will be opened as it is.'
                    : 'This folder is empty. A new workspace will be created in it.'}
                </p>

                {candidate.warnings.map((warning) => (
                  <p
                    key={warning.kind}
                    style={{
                      margin: 0,
                      fontSize: '0.875rem',
                      lineHeight: 1.6,
                      color: '#fbbf24',
                    }}
                  >
                    {warningText(warning)}
                  </p>
                ))}

                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button
                    type="button"
                    style={button('primary')}
                    onClick={() => void confirm()}
                    disabled={busy}
                  >
                    {/* Q14's "choose anyway". The warning is shown, and then
                        the user's decision stands. */}
                    {candidate.warnings.length > 0 ? 'Use this folder anyway' : 'Use this folder'}
                  </button>
                  <button type="button" style={button()} onClick={() => setCandidate(null)}>
                    Cancel
                  </button>
                </div>
              </>
            )}
          </section>
        ) : null}
      </div>
    </main>
  );
}
