import { useEffect, useState } from 'react';
import { FolderOpen, Pencil, Trash2 } from 'lucide-react';
import { open } from '@tauri-apps/plugin-dialog';

import { errorMessage } from '@/core/api/error-message';
import type { RecordingDetail, ValidationIssue } from '@/core/api/types';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/core/components/ui/table';
import { InlineError } from '@/core/ui/InlineError';
import {
  useDeleteRecording,
  useRelocateAsset,
  useUpdateRecording,
} from '@/modules/video-composer/api/campaigns';
import { formatDurationMs, formatResolution } from '@/modules/video-composer/lib/format-media';
import { VIDEO_PICKER_FILTERS } from '@/modules/video-composer/lib/media-constants';
import { warningIssuesForAsset } from '@/modules/video-composer/lib/validation';
import { RecordingWarningIndicators } from '@/modules/video-composer/components/RecordingWarningIndicators';

interface Props {
  campaignId: string;
  recordings: RecordingDetail[];
  validationIssues: ValidationIssue[];
}

function CompanyNameCell({
  campaignId,
  recording,
}: {
  campaignId: string;
  recording: RecordingDetail;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(recording.company_name);
  const [validationError, setValidationError] = useState<string | null>(null);
  const updateRecording = useUpdateRecording();

  useEffect(() => {
    setDraft(recording.company_name);
  }, [recording.company_name]);

  const cancel = () => {
    setDraft(recording.company_name);
    setValidationError(null);
    setEditing(false);
  };

  const commit = () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      setValidationError('A company name cannot be empty.');
      return;
    }

    if (trimmed === recording.company_name) {
      cancel();
      return;
    }

    setValidationError(null);
    updateRecording.mutate(
      { campaignId, recordingId: recording.id, company_name: trimmed },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => setValidationError(errorMessage(error)),
      },
    );
  };

  if (editing) {
    return (
      <div className="min-w-0 space-y-1">
        <Input
          autoFocus
          value={draft}
          aria-label="Company name"
          aria-invalid={validationError != null}
          disabled={updateRecording.isPending}
          className="h-8 rounded-xl"
          onChange={(event) => {
            setDraft(event.target.value);
            if (validationError) {
              setValidationError(null);
            }
          }}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commit();
            }
            if (event.key === 'Escape') {
              event.preventDefault();
              cancel();
            }
          }}
        />
        <InlineError message={validationError} className="text-xs text-destructive" />
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1">
        <span className="min-w-0 truncate font-medium">{recording.company_name}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Rename ${recording.company_name}`}
          onClick={() => setEditing(true)}
        >
          <Pencil aria-hidden />
        </Button>
      </div>
      <p className="truncate text-xs text-muted-foreground">{recording.source_filename}</p>
    </div>
  );
}

function RecordingActionsCell({
  campaignId,
  recording,
}: {
  campaignId: string;
  recording: RecordingDetail;
}) {
  const deleteRecording = useDeleteRecording();
  const relocateAsset = useRelocateAsset();
  const [relocateError, setRelocateError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleRelocate = async () => {
    setRelocateError(null);
    const selected = await open({
      multiple: false,
      title: `Relocate ${recording.company_name}`,
      filters: VIDEO_PICKER_FILTERS,
    });

    if (typeof selected !== 'string') {
      return;
    }

    relocateAsset.mutate(
      { campaignId, assetId: recording.id, source_path: selected },
      {
        onError: (error) => setRelocateError(errorMessage(error)),
      },
    );
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1">
        {recording.file_missing ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={relocateAsset.isPending}
            onClick={() => void handleRelocate()}
            data-icon="inline-start"
          >
            <FolderOpen aria-hidden />
            Relocate
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Remove ${recording.company_name}`}
          disabled={deleteRecording.isPending}
          onClick={() => {
            setDeleteError(null);
            deleteRecording.mutate(
              { campaignId, recordingId: recording.id },
              { onError: (error) => setDeleteError(errorMessage(error)) },
            );
          }}
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
      <InlineError
        message={relocateError ?? deleteError}
        className="max-w-48 text-right text-xs text-destructive"
      />
    </div>
  );
}

export function RecordingsTable({ campaignId, recordings, validationIssues }: Props) {
  if (recordings.length === 0) {
    return (
      <p className="mt-4 text-sm text-muted-foreground">
        No screen recordings yet. Drop files above to add them.
      </p>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead>Company</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Resolution</TableHead>
            <TableHead>Output file</TableHead>
            <TableHead>
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {recordings.map((recording) => {
            const warnings = warningIssuesForAsset(validationIssues, recording.id);
            return (
              <TableRow key={recording.id} data-missing={recording.file_missing || undefined}>
                <TableCell className="max-w-xs whitespace-normal">
                  <CompanyNameCell campaignId={campaignId} recording={recording} />
                  {recording.file_missing ? (
                    <p className="mt-1 text-xs font-medium text-destructive">File missing</p>
                  ) : null}
                  <RecordingWarningIndicators issues={warnings} />
                </TableCell>
                <TableCell className="tabular-nums text-muted-foreground">
                  {recording.file_missing
                    ? '—'
                    : recording.probe_status === 'ok' && recording.duration_ms != null
                      ? formatDurationMs(recording.duration_ms)
                      : (recording.probe_error ?? 'Unreadable')}
                </TableCell>
                <TableCell className="tabular-nums text-muted-foreground">
                  {recording.file_missing
                    ? '—'
                    : recording.probe_status === 'ok' &&
                        recording.width != null &&
                        recording.height != null
                      ? formatResolution(recording.width, recording.height)
                      : '—'}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {recording.output_basename}.mp4
                </TableCell>
                <TableCell className="text-right">
                  <RecordingActionsCell campaignId={campaignId} recording={recording} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
