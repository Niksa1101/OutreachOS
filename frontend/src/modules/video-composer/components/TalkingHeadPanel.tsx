import { useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { Film, FolderOpen } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import { Button } from '@/core/components/ui/button';
import type { TalkingHeadDetail } from '@/core/api/types';
import { InlineError } from '@/core/ui/InlineError';
import {
  formatDurationMs,
  formatFps,
  formatResolution,
} from '@/modules/video-composer/lib/format-media';
import { VIDEO_PICKER_FILTERS } from '@/modules/video-composer/lib/media-constants';
import { useAssignTalkingHead, useRelocateAsset } from '@/modules/video-composer/api/campaigns';

interface Props {
  campaignId: string;
  talkingHead: TalkingHeadDetail | null;
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

export function TalkingHeadPanel({ campaignId, talkingHead }: Props) {
  const assignTalkingHead = useAssignTalkingHead();
  const relocateAsset = useRelocateAsset();
  const [pickError, setPickError] = useState<string | null>(null);

  const isMissing = talkingHead?.file_missing ?? false;
  const isPending = assignTalkingHead.isPending || relocateAsset.isPending;

  const handlePick = async () => {
    setPickError(null);
    const selected = await open({
      multiple: false,
      title: isMissing ? 'Relocate the talking-head video' : 'Choose a talking-head video',
      filters: VIDEO_PICKER_FILTERS,
    });

    if (typeof selected !== 'string') {
      return;
    }

    const onError = (error: Error) => setPickError(errorMessage(error));

    if (talkingHead && isMissing) {
      relocateAsset.mutate(
        { campaignId, assetId: talkingHead.id, source_path: selected },
        { onError },
      );
      return;
    }

    assignTalkingHead.mutate({ campaignId, source_path: selected }, { onError });
  };

  const assignError =
    assignTalkingHead.error != null ? errorMessage(assignTalkingHead.error) : null;
  const relocateError = relocateAsset.error != null ? errorMessage(relocateAsset.error) : null;
  const errorMessageText = pickError ?? relocateError ?? assignError;

  const actionLabel = talkingHead ? (isMissing ? 'Relocate' : 'Replace') : 'Choose video';

  return (
    <section className="rounded-2xl border border-border p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Talking head</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            One reusable presenter video for this campaign. The file stays where it is on disk.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant={talkingHead && !isMissing ? 'outline' : 'default'}
          disabled={isPending}
          onClick={() => void handlePick()}
          data-icon="inline-start"
        >
          <FolderOpen aria-hidden />
          {actionLabel}
        </Button>
      </div>

      <InlineError message={errorMessageText} className="mt-4 text-sm text-destructive" />

      {talkingHead ? (
        <>
          {isMissing ? (
            <p className="mt-4 text-sm font-medium text-destructive" role="status">
              File missing — the source file is no longer at its saved path.
            </p>
          ) : null}
          <dl className="mt-5 grid gap-3 rounded-xl bg-muted/40 p-4">
            <MetadataRow label="File" value={talkingHead.source_filename} />
            <MetadataRow label="Duration" value={formatDurationMs(talkingHead.duration_ms)} />
            <MetadataRow
              label="Resolution"
              value={formatResolution(talkingHead.width, talkingHead.height)}
            />
            <MetadataRow label="Frame rate" value={formatFps(talkingHead.fps)} />
            <MetadataRow label="Codec" value={talkingHead.video_codec} />
            <MetadataRow label="Audio" value={talkingHead.has_audio ? 'Yes' : 'No'} />
          </dl>
        </>
      ) : (
        <div className="mt-5 flex items-center gap-3 rounded-xl border border-dashed border-border px-4 py-8 text-sm text-muted-foreground">
          <Film aria-hidden className="size-5 shrink-0 opacity-60" />
          <p>No talking head assigned yet. Choose a video to probe and store its metadata.</p>
        </div>
      )}
    </section>
  );
}
