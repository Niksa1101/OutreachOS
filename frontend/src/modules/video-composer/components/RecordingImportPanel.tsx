import { useCallback, useEffect, useState } from 'react';
import { getCurrentWebview } from '@tauri-apps/api/webview';
import { open } from '@tauri-apps/plugin-dialog';
import { FolderOpen, Upload } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import { Button } from '@/core/components/ui/button';
import type { RecordingImportRejected } from '@/core/api/types';
import { InlineError } from '@/core/ui/InlineError';
import { useImportRecordings } from '@/modules/video-composer/api/campaigns';
import { isVideoPath, VIDEO_PICKER_FILTERS } from '@/modules/video-composer/lib/media-constants';

interface Props {
  campaignId: string;
}

function formatImportIssues(items: RecordingImportRejected[]): string {
  return items
    .map((item) => `${item.source_path.split(/[\\/]/).pop() ?? item.source_path}: ${item.message}`)
    .join('\n');
}

export function RecordingImportPanel({ campaignId }: Props) {
  const importRecordings = useImportRecordings();
  const [dragActive, setDragActive] = useState(false);
  const [issueMessage, setIssueMessage] = useState<string | null>(null);
  const [pickError, setPickError] = useState<string | null>(null);

  const importPaths = useCallback(
    (paths: string[]) => {
      const videoPaths = paths.filter(isVideoPath);
      if (videoPaths.length === 0) {
        setPickError('Choose one or more video files to import.');
        return;
      }

      setPickError(null);
      setIssueMessage(null);
      importRecordings.mutate(
        { campaignId, source_paths: videoPaths },
        {
          onSuccess: (result) => {
            const issues = [...result.rejected, ...result.failed];
            if (issues.length > 0) {
              setIssueMessage(formatImportIssues(issues));
            }
          },
          onError: (error) => setPickError(errorMessage(error)),
        },
      );
    },
    [campaignId, importRecordings],
  );

  useEffect(() => {
    if (!('__TAURI_INTERNALS__' in window)) {
      return;
    }

    let cancelled = false;
    let unlisten: (() => void) | null = null;

    void getCurrentWebview()
      .onDragDropEvent((event) => {
        if (event.payload.type === 'over') {
          setDragActive(true);
          return;
        }

        setDragActive(false);
        if (event.payload.type !== 'drop') {
          return;
        }

        importPaths(event.payload.paths);
      })
      .then((dispose) => {
        if (cancelled) {
          dispose();
          return;
        }
        unlisten = dispose;
      });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [importPaths]);

  const handlePick = async () => {
    setPickError(null);
    const selected = await open({
      multiple: true,
      title: 'Choose screen recordings',
      filters: VIDEO_PICKER_FILTERS,
    });

    if (!selected) {
      return;
    }

    const paths = Array.isArray(selected) ? selected : [selected];
    importPaths(paths);
  };

  const mutationError =
    importRecordings.error != null ? errorMessage(importRecordings.error) : null;
  const errorMessageText = pickError ?? mutationError;

  return (
    <section className="rounded-2xl border border-border p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Screen recordings</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Drop many files at once or browse. Each file is probed in parallel and company names
            come from the filename.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={importRecordings.isPending}
          onClick={() => void handlePick()}
          data-icon="inline-start"
        >
          <FolderOpen aria-hidden />
          Browse files
        </Button>
      </div>

      <div
        className={`mt-5 flex flex-col items-center justify-center rounded-xl border border-dashed px-4 py-10 text-center text-sm transition-colors ${
          dragActive
            ? 'border-primary bg-primary/5 text-foreground'
            : 'border-border text-muted-foreground'
        }`}
      >
        <Upload aria-hidden className="mb-3 size-6 opacity-60" />
        <p>{importRecordings.isPending ? 'Probing recordings…' : 'Drop screen recordings here'}</p>
      </div>

      <InlineError
        message={errorMessageText}
        className="mt-4 whitespace-pre-wrap text-sm text-destructive"
      />

      {issueMessage ? (
        <p
          className="mt-4 whitespace-pre-wrap text-sm text-amber-700 dark:text-amber-300"
          role="status"
        >
          {issueMessage}
        </p>
      ) : null}
    </section>
  );
}
