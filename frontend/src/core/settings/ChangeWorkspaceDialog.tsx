/**
 * Ticket 26: change where the workspace lives from Settings.
 *
 * Relocation is blocked while any queue activity exists. The user chooses
 * Move existing or Start fresh before Rust stops the backend and switches the
 * pointer only after the file operation succeeds.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import { open as pickFolder } from '@tauri-apps/plugin-dialog';

import { apiFetch } from '@/core/api/client';
import type { RenderQueueResponse } from '@/core/api/types';
import { Button } from '@/core/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/core/components/ui/dialog';
import { useRenderQueueActiveCount } from '@/core/hooks/useRenderQueueActiveCount';

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

type RelocateMode = 'move_existing' | 'start_fresh';

const REJECTION_TEXT: Record<WorkspaceRejection, string> = {
  not_found: 'That folder no longer exists.',
  not_a_directory: 'That is a file, not a folder.',
  not_writable:
    'OutreachOS cannot write there. Protected locations such as Program Files need administrator rights, which this app deliberately never asks for.',
  not_empty:
    'That folder already contains other files. Pick an empty folder, or one that already holds an OutreachOS workspace when moving your data.',
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
      return `This folder is inside ${warning.provider ?? 'a cloud-sync folder'}. The sync client can rewrite files while OutreachOS has the database open, which can corrupt it.`;
    case 'network_drive':
      return 'This folder is on a network drive. SQLite file locking over a network share is unreliable.';
    case 'unc_path':
      return 'This is a network path. SQLite file locking over a network share is unreliable.';
    case 'path_length':
      return `This path is ${warning.length ?? 0} characters. OutreachOS writes files several levels below it, and long paths can hit the Windows limit.`;
  }
}

interface Props {
  currentPath: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChangeWorkspaceDialog({ currentPath, open, onOpenChange }: Props) {
  const activeJobCount = useRenderQueueActiveCount();
  const queueBlocked = activeJobCount > 0;

  const [candidate, setCandidate] = useState<WorkspaceValidation | null>(null);
  const [mode, setMode] = useState<RelocateMode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Warm the render-queue query when the dialog opens so the block reason is fresh.
  useQuery({
    queryKey: ['render-queue'],
    queryFn: () => apiFetch<RenderQueueResponse>('/render-queue'),
    enabled: open,
  });

  function reset() {
    setCandidate(null);
    setMode(null);
    setError(null);
  }

  function handleOpenChange(next: boolean) {
    if (!next) reset();
    onOpenChange(next);
  }

  async function chooseFolder() {
    setError(null);
    const selected = await pickFolder({
      directory: true,
      multiple: false,
      title: 'Choose a new workspace location',
    });
    if (typeof selected !== 'string') return;

    setBusy(true);
    try {
      const validation = await invoke<WorkspaceValidation>('validate_workspace', {
        path: selected,
      });
      setCandidate(validation);
      setMode(null);
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!candidate || candidate.rejection || !mode) return;

    setBusy(true);
    setError(null);
    try {
      await invoke('relocate_workspace', {
        targetPath: candidate.path,
        mode,
      });
      handleOpenChange(false);
    } catch {
      handleOpenChange(false);
    } finally {
      setBusy(false);
    }
  }

  const canConfirm =
    candidate !== null && !candidate.rejection && mode !== null && !queueBlocked && !busy;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Change workspace location</DialogTitle>
          <DialogDescription>
            OutreachOS keeps its database, cache, rendered videos, and logs in one folder. Choose
            where that folder should live, then pick how to handle your existing data.
          </DialogDescription>
        </DialogHeader>

        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Current</dt>
          <dd className="font-mono break-all">{currentPath}</dd>
        </dl>

        {queueBlocked ? (
          <p className="text-sm text-amber-400" role="alert">
            Relocation is unavailable while {activeJobCount}{' '}
            {activeJobCount === 1 ? 'job is' : 'jobs are'} waiting or in progress in the render
            queue. Pause or wait for the queue to finish, then try again.
          </p>
        ) : null}

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {!candidate ? (
          <Button type="button" onClick={() => void chooseFolder()} disabled={busy || queueBlocked}>
            Choose folder…
          </Button>
        ) : (
          <section className="space-y-3 rounded-2xl border border-border p-4">
            <p className="font-mono text-sm break-all opacity-80">{candidate.path}</p>

            {candidate.rejection ? (
              <p className="text-sm text-destructive">{REJECTION_TEXT[candidate.rejection]}</p>
            ) : (
              <>
                {candidate.warnings.map((warning) => (
                  <p key={warning.kind} className="text-sm text-amber-400">
                    {warningText(warning)}
                  </p>
                ))}

                <div className="space-y-2">
                  <p className="text-sm font-medium">What should happen to your existing workspace?</p>
                  {candidate.existing ? (
                    <p className="text-sm text-destructive">
                      This folder already holds an OutreachOS workspace. Pick an empty folder to move
                      or start fresh.
                    </p>
                  ) : (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <ModeOption
                        title="Move existing"
                        description="Copy the database, cache, and staged outputs to the new location. Your original folder stays on disk until you delete it."
                        selected={mode === 'move_existing'}
                        disabled={busy || queueBlocked}
                        onSelect={() => setMode('move_existing')}
                      />
                      <ModeOption
                        title="Start fresh"
                        description="Create a new empty workspace at the new location. Your original folder is left untouched on disk."
                        selected={mode === 'start_fresh'}
                        disabled={busy || queueBlocked}
                        onSelect={() => setMode('start_fresh')}
                      />
                    </div>
                  )}
                </div>
              </>
            )}
          </section>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          {candidate && !candidate.rejection ? (
            <Button type="button" onClick={() => void confirm()} disabled={!canConfirm}>
              {busy ? 'Moving…' : 'Change location'}
            </Button>
          ) : candidate ? (
            <Button type="button" variant="outline" onClick={() => setCandidate(null)} disabled={busy}>
              Pick a different folder
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ModeOption({
  title,
  description,
  selected,
  disabled,
  onSelect,
}: {
  title: string;
  description: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      className={[
        'rounded-2xl border p-3 text-left text-sm transition-colors',
        selected
          ? 'border-primary bg-primary/10'
          : 'border-border bg-background hover:bg-muted/50',
        disabled ? 'cursor-not-allowed opacity-50' : '',
      ].join(' ')}
    >
      <span className="block font-medium">{title}</span>
      <span className="mt-1 block text-muted-foreground">{description}</span>
    </button>
  );
}
