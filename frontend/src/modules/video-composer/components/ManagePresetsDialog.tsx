import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/core/components/ui/alert-dialog';
import { Button } from '@/core/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/core/components/ui/dialog';
import { Input } from '@/core/components/ui/input';
import { Skeleton } from '@/core/components/ui/skeleton';
import { InlineError } from '@/core/ui/InlineError';
import {
  presetsListQuery,
  useDeletePreset,
  useRenamePreset,
} from '@/modules/video-composer/api/campaigns';
import type { OverlayPresetSummary } from '@/core/api/types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ManagePresetsDialog({ open, onOpenChange }: Props) {
  const presets = useQuery({ ...presetsListQuery, enabled: open });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Manage presets</DialogTitle>
          <DialogDescription>
            Renaming or deleting a preset never changes campaigns that already applied it.
          </DialogDescription>
        </DialogHeader>

        {presets.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : presets.isError ? (
          <p className="text-sm text-destructive">Could not load presets. Try again in a moment.</p>
        ) : presets.data && presets.data.presets.length > 0 ? (
          <ul className="space-y-2">
            {presets.data.presets.map((preset) => (
              <PresetRow key={preset.id} preset={preset} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No presets saved yet.</p>
        )}

        <DialogFooter showCloseButton />
      </DialogContent>
    </Dialog>
  );
}

function PresetRow({ preset }: { preset: OverlayPresetSummary }) {
  const [name, setName] = useState(preset.name);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const renamePreset = useRenamePreset();
  const deletePreset = useDeletePreset();

  const trimmed = name.trim();
  const dirty = trimmed.length > 0 && trimmed !== preset.name;

  function handleRename() {
    if (!dirty) return;
    setError(null);
    renamePreset.mutate(
      { id: preset.id, name: trimmed },
      { onError: (err) => setError(errorMessage(err)) },
    );
  }

  function handleDelete() {
    setError(null);
    deletePreset.mutate(preset.id, {
      onSuccess: () => setConfirmingDelete(false),
      onError: (err) => setError(errorMessage(err)),
    });
  }

  return (
    <li className="space-y-1">
      <div className="flex items-center gap-2">
        <Input
          value={name}
          maxLength={200}
          onChange={(event) => setName(event.target.value)}
          onBlur={handleRename}
          onKeyDown={(event) => {
            if (event.key === 'Enter') handleRename();
          }}
          disabled={renamePreset.isPending || deletePreset.isPending}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Delete preset "${preset.name}"`}
          disabled={deletePreset.isPending}
          onClick={() => setConfirmingDelete(true)}
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
      <InlineError message={error} className="text-xs text-destructive" />

      <AlertDialog open={confirmingDelete} onOpenChange={setConfirmingDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{preset.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. Campaigns that already applied this preset keep their copy of
              its values unchanged.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletePreset.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deletePreset.isPending}
              onClick={handleDelete}
            >
              Delete preset
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}
