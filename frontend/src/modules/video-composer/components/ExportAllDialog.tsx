import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { open as pickFolder } from '@tauri-apps/plugin-dialog';
import { FolderOpen } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/core/components/ui/alert-dialog';
import { Button } from '@/core/components/ui/button';
import { Skeleton } from '@/core/components/ui/skeleton';
import { InlineError } from '@/core/ui/InlineError';
import {
  campaignOutputsQuery,
  useExportAll,
} from '@/modules/video-composer/api/export';
import {
  describeExportConfirmation,
  describeExportableCount,
  describeExportResult,
} from '@/modules/video-composer/lib/export';

interface Props {
  campaignId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onExported?: (notice: string | null) => void;
}

export function ExportAllDialog({ campaignId, open, onOpenChange, onExported }: Props) {
  const exportAll = useExportAll();
  const [destinationPath, setDestinationPath] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pickerError, setPickerError] = useState<string | null>(null);

  const outputs = useQuery({
    ...campaignOutputsQuery(campaignId),
    enabled: open,
  });

  const busy = exportAll.isPending;
  const exportableCount = outputs.data?.exportable_count ?? 0;
  const seedPath = outputs.data?.default_export_path ?? undefined;

  useEffect(() => {
    if (!open || !seedPath || destinationPath) return;
    setDestinationPath(seedPath);
  }, [open, seedPath, destinationPath]);

  async function chooseFolder() {
    setPickerError(null);
    try {
      const defaultPath = destinationPath ?? seedPath;
      const selected = await pickFolder({
        directory: true,
        multiple: false,
        title: 'Choose export folder',
        ...(defaultPath ? { defaultPath } : {}),
      });
      if (typeof selected === 'string') {
        setDestinationPath(selected);
      }
    } catch (cause) {
      setPickerError(String(cause));
    }
  }

  function runExport() {
    if (!destinationPath) return;
    setActionError(null);
    exportAll.mutate(
      { campaignId, destination_path: destinationPath },
      {
        onSuccess: (result) => {
          onOpenChange(false);
          setDestinationPath(null);
          onExported?.(
            describeExportResult(
              result.moved_count,
              result.conflicts ?? [],
              result.failures ?? [],
            ),
          );
        },
        onError: (error) => setActionError(errorMessage(error)),
      },
    );
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setDestinationPath(null);
          setActionError(null);
          setPickerError(null);
        }
        onOpenChange(next);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Export all completed renders?</AlertDialogTitle>
          <AlertDialogDescription>
            Files move out of the workspace staging area — they are not copied. Completed queue
            rows clear after a successful export; failed jobs stay until you dismiss them.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {outputs.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        ) : outputs.isError ? (
          <p className="text-sm text-destructive">
            Could not load staged outputs. Try again in a moment.
          </p>
        ) : outputs.data ? (
          <div className="space-y-3 text-sm">
            <p role="status">{describeExportableCount(outputs.data.exportable_count)}</p>
            <div className="space-y-2">
              <p className="text-muted-foreground">Destination folder</p>
              <p className="break-all font-mono text-xs text-foreground">
                {destinationPath ?? seedPath ?? 'Not selected'}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                data-icon="inline-start"
                onClick={() => void chooseFolder()}
              >
                <FolderOpen aria-hidden />
                Choose folder
              </Button>
            </div>
            {destinationPath ? (
              <p role="status">{describeExportConfirmation(exportableCount, destinationPath)}</p>
            ) : null}
          </div>
        ) : null}

        <InlineError message={pickerError} className="text-sm text-destructive" />
        <InlineError message={actionError} className="text-sm text-destructive" />

        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <Button
            type="button"
            disabled={
              outputs.isPending ||
              outputs.isError ||
              busy ||
              exportableCount === 0 ||
              !destinationPath
            }
            onClick={runExport}
          >
            {busy ? 'Exporting…' : 'Export All'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
