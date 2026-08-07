/**
 * Settings — ticket 25.
 *
 * Global quality preset, encoder override, cache management, bundled FFmpeg
 * version, and the default export folder that seeds the export picker.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { open } from '@tauri-apps/plugin-dialog';
import { FolderOpen, Trash2 } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import { settingsQuery } from '@/core/api/queries';
import { useClearCache, useUpdateSettings } from '@/core/api/settings';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Skeleton } from '@/core/components/ui/skeleton';
import { formatBytes } from '@/core/lib/format';
import { ChangeWorkspaceDialog } from '@/core/settings/ChangeWorkspaceDialog';
import { InlineError } from '@/core/ui/InlineError';

const QUALITY_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'standard', label: 'Standard' },
  { value: 'high', label: 'High' },
] as const;

const ENCODER_LABELS: Record<string, string> = {
  h264_nvenc: 'NVIDIA NVENC',
  h264_qsv: 'Intel Quick Sync',
  h264_amf: 'AMD AMF',
  libx264: 'Software (libx264)',
};

const QUEUE_BUSY_REASON =
  'Changes are locked while the render queue has waiting or active jobs.';

function encoderLabel(name: string): string {
  return ENCODER_LABELS[name] ?? name;
}

export function SettingsScreen() {
  const { data, error, isPending } = useQuery(settingsQuery);
  const updateSettings = useUpdateSettings();
  const clearCache = useClearCache();
  const [clearOpen, setClearOpen] = useState(false);
  const [relocateOpen, setRelocateOpen] = useState(false);

  const detectedEncoders: string[] = (() => {
    if (!data?.detected_encoders) return [];
    try {
      const parsed = JSON.parse(data.detected_encoders) as unknown;
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  })();

  async function pickExportFolder() {
    const selected = await open({
      directory: true,
      multiple: false,
      ...(data?.default_export_path ? { defaultPath: data.default_export_path } : {}),
      title: 'Choose default export folder',
    });
    if (typeof selected === 'string') {
      updateSettings.mutate({ default_export_path: selected });
    }
  }

  if (isPending) {
    return (
      <div className="p-6 max-w-2xl space-y-6">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive" role="alert">
          {error ? errorMessage(error) : 'Settings could not be loaded.'}
        </p>
      </div>
    );
  }

  const encoderValue = data.encoder_override ?? 'auto';
  const queueLocked = data.queue_busy;

  return (
    <div className="p-6 max-w-2xl space-y-8">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Global defaults for rendering and export. Campaigns inherit these unless overridden.
        </p>
      </header>

      <section className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Rendering</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Quality and encoder defaults applied to every campaign.
          </p>
        </div>

        {queueLocked ? (
          <p className="text-sm text-amber-400" role="status">
            {QUEUE_BUSY_REASON}
          </p>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-[max-content_1fr] sm:items-center">
          <label htmlFor="quality-preset" className="text-sm text-muted-foreground">
            Quality preset
          </label>
          <Select
            value={data.quality_preset}
            disabled={queueLocked || updateSettings.isPending}
            onValueChange={(value) => {
              if (value !== 'draft' && value !== 'standard' && value !== 'high') return;
              updateSettings.mutate({ quality_preset: value });
            }}
          >
            <SelectTrigger id="quality-preset" className="w-full sm:max-w-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {QUALITY_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <label htmlFor="encoder-override" className="text-sm text-muted-foreground">
            Encoder
          </label>
          <div className="space-y-1">
            <Select
              value={encoderValue}
              disabled={queueLocked || updateSettings.isPending}
              onValueChange={(value) => {
                if (!value) return;
                updateSettings.mutate({
                  encoder_override: value === 'auto' ? null : value,
                });
              }}
            >
              <SelectTrigger id="encoder-override" className="w-full sm:max-w-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">
                  Auto-detect
                  {data.detected_encoder
                    ? ` (${encoderLabel(data.detected_encoder)})`
                    : ''}
                </SelectItem>
                {detectedEncoders.map((encoder) => (
                  <SelectItem key={encoder} value={encoder}>
                    {encoderLabel(encoder)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {data.detected_encoder ? (
              <p className="text-xs text-muted-foreground">
                Detected default: {encoderLabel(data.detected_encoder)}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">Encoder detection runs at startup.</p>
            )}
          </div>

          <span className="text-sm text-muted-foreground">FFmpeg</span>
          <p className="font-mono text-sm break-all">{data.ffmpeg_version ?? 'Not probed yet'}</p>

          <span className="text-sm text-muted-foreground">Cache</span>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm">{formatBytes(data.cache_size_bytes)}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-icon="inline-start"
              disabled={queueLocked || data.cache_size_bytes === 0 || clearCache.isPending}
              onClick={() => setClearOpen(true)}
            >
              <Trash2 aria-hidden />
              Clear cache
            </Button>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Export</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The default folder that seeds the export picker.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-mono text-sm break-all text-muted-foreground">
            {data.default_export_path ?? 'Not set'}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-icon="inline-start"
            disabled={updateSettings.isPending}
            onClick={() => void pickExportFolder()}
          >
            <FolderOpen aria-hidden />
            Choose folder
          </Button>
          {data.default_export_path ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={updateSettings.isPending}
              onClick={() => updateSettings.mutate({ default_export_path: null })}
            >
              Clear
            </Button>
          ) : null}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold tracking-tight">Workspace</h2>
        <dl className="grid gap-2 text-sm">
          <div>
            <dt className="text-muted-foreground">Path</dt>
            <dd className="font-mono break-all">{data.workspace_path}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Database revision</dt>
            <dd className="font-mono">{data.migration_head ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Log</dt>
            <dd className="font-mono break-all">{data.backend_log_path}</dd>
          </div>
        </dl>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={queueLocked}
          onClick={() => setRelocateOpen(true)}
        >
          Change location…
        </Button>
        <ChangeWorkspaceDialog
          currentPath={data.workspace_path}
          open={relocateOpen}
          onOpenChange={setRelocateOpen}
        />
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold tracking-tight">Build</h2>
        <dl className="grid gap-2 text-sm">
          <div>
            <dt className="text-muted-foreground">Application</dt>
            <dd className="font-mono">{data.app_version ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Backend</dt>
            <dd className="font-mono">{data.backend_version}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Boot</dt>
            <dd className="font-mono">{data.boot_id}</dd>
          </div>
        </dl>
      </section>

      <InlineError
        message={updateSettings.error ? errorMessage(updateSettings.error) : null}
        className="text-sm text-destructive"
      />
      <InlineError
        message={clearCache.error ? errorMessage(clearCache.error) : null}
        className="text-sm text-destructive"
      />

      <AlertDialog open={clearOpen} onOpenChange={setClearOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear render cache?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes all cached alpha clips and overlay assets ({formatBytes(data.cache_size_bytes)}).
              The next batch will rebuild them from scratch.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                clearCache.mutate(undefined, {
                  onSuccess: () => setClearOpen(false),
                });
              }}
            >
              Clear cache
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
