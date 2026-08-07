import { useEffect, useState } from 'react';
import { Link, useMatch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Play } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import { Button } from '@/core/components/ui/button';
import { Skeleton } from '@/core/components/ui/skeleton';
import { InlineError } from '@/core/ui/InlineError';
import {
  campaignDetailQuery,
  useUpdateOverlayConfig,
} from '@/modules/video-composer/api/campaigns';
import { CampaignPreviewPane } from '@/modules/video-composer/components/CampaignPreviewPane';
import { EditorLockBanner } from '@/modules/video-composer/components/EditorLockBanner';
import { GenerateVideosDialog } from '@/modules/video-composer/components/GenerateVideosDialog';
import { OutputsSection } from '@/modules/video-composer/components/OutputsSection';
import { OverlayGeometryForm } from '@/modules/video-composer/components/OverlayGeometryForm';
import { PresetControls } from '@/modules/video-composer/components/PresetControls';
import { QualityOverrideControl } from '@/modules/video-composer/components/QualityOverrideControl';
import { RecordingImportPanel } from '@/modules/video-composer/components/RecordingImportPanel';
import { RecordingsTable } from '@/modules/video-composer/components/RecordingsTable';
import { TalkingHeadEditor } from '@/modules/video-composer/components/TalkingHeadEditor';
import { TalkingHeadPanel } from '@/modules/video-composer/components/TalkingHeadPanel';
import { ValidationSummary } from '@/modules/video-composer/components/ValidationSummary';
import {
  parseOverlayConfig,
  type OverlayConfig,
} from '@/modules/video-composer/lib/overlay-geometry';

export function CampaignDetailScreen() {
  const { campaignId } = useMatch({ strict: false }).params as { campaignId: string };
  const { data, isPending, isError } = useQuery(campaignDetailQuery(campaignId));
  const updateOverlay = useUpdateOverlayConfig();
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generateNotice, setGenerateNotice] = useState<string | null>(null);
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  // Local draft, live-synced with drag/resize/typed input; only re-derived
  // from the server when the persisted config itself changes (not on every
  // unrelated campaign-detail refetch), so mid-drag/mid-typing state is
  // never clobbered by e.g. an import elsewhere on the page.
  const [overlay, setOverlay] = useState<OverlayConfig>(() =>
    parseOverlayConfig(data?.overlay_config),
  );
  useEffect(() => {
    if (data) setOverlay(parseOverlayConfig(data.overlay_config));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.overlay_config]);

  function commitOverlay(next: OverlayConfig) {
    setOverlay(next);
    if (data && !data.is_locked) updateOverlay.mutate({ campaignId: data.id, overlay: next });
  }

  if (isPending) {
    return (
      <div className="p-6">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="mt-6 h-56 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6">
        <Button variant="ghost" size="sm" render={<Link to="/video-composer/campaigns" />}>
          <ArrowLeft aria-hidden />
          Back to campaigns
        </Button>
        <p className="mt-4 text-sm text-muted-foreground">
          Could not load this campaign. It may have been deleted.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-8 p-6 lg:grid-cols-[minmax(0,1fr)_420px]">
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" render={<Link to="/video-composer/campaigns" />}>
            <ArrowLeft aria-hidden />
            Campaigns
          </Button>
        </div>

        <header className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">{data.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Assign the reusable talking-head video this campaign composites onto its screen
              recordings.
            </p>
          </div>
          <Button
            type="button"
            disabled={!data.validation.can_generate}
            title={data.validation.generate_blocked_reason ?? undefined}
            aria-describedby={
              data.validation.generate_blocked_reason ? 'generate-blocked-reason' : undefined
            }
            data-icon="inline-start"
            onClick={() => {
              setGenerateNotice(null);
              setGenerateOpen(true);
            }}
          >
            <Play aria-hidden />
            Generate Videos
          </Button>
        </header>

        {data.validation.generate_blocked_reason ? (
          <p
            id="generate-blocked-reason"
            className="mt-3 text-sm text-muted-foreground"
            role="status"
          >
            {data.validation.generate_blocked_reason}
          </p>
        ) : null}

        {generateNotice ? (
          <p className="mt-3 text-sm text-muted-foreground" role="status">
            {generateNotice}
          </p>
        ) : null}

        <GenerateVideosDialog
          campaignId={data.id}
          open={generateOpen}
          onOpenChange={setGenerateOpen}
          onQueued={setGenerateNotice}
        />

        {data.is_locked && data.lock_reason ? (
          <div className="mt-4">
            <EditorLockBanner campaignId={data.id} reason={data.lock_reason} />
          </div>
        ) : null}

        <div className="mt-4">
          <ValidationSummary validation={data.validation} />
        </div>

        <div className="mt-6 space-y-6">
          <TalkingHeadPanel campaignId={data.id} talkingHead={data.talking_head ?? null} />
          {data.talking_head ? (
            <TalkingHeadEditor
              campaignId={data.id}
              talkingHead={data.talking_head}
              overlay={overlay}
              locked={data.is_locked}
            />
          ) : null}
          <RecordingImportPanel campaignId={data.id} />
          <QualityOverrideControl
            campaignId={data.id}
            qualityOverride={data.quality_override ?? null}
            locked={data.is_locked}
          />
          <RecordingsTable
            campaignId={data.id}
            recordings={data.recordings ?? []}
            validationIssues={data.validation.issues ?? []}
          />
          <OutputsSection
            campaignId={data.id}
            exportNotice={exportNotice}
            onExportNotice={setExportNotice}
          />
        </div>
      </div>

      {/* `self-start`: without it the grid stretches this column to match the
          left column's height, leaving no room for `sticky` to have any
          scrolling left to pin against. */}
      <div className="lg:sticky lg:top-6 lg:self-start space-y-6">
        <CampaignPreviewPane
          campaignId={data.id}
          overlay={overlay}
          onOverlayChange={setOverlay}
          onOverlayCommit={commitOverlay}
          locked={data.is_locked}
        />
        <section>
          <h2 className="text-sm font-semibold tracking-tight">Overlay geometry</h2>
          <div className="mt-3">
            <PresetControls
              campaignId={data.id}
              overlay={overlay}
              onApplied={setOverlay}
              locked={data.is_locked}
            />
          </div>
          <div className="mt-4">
            <OverlayGeometryForm
              overlay={overlay}
              onChange={setOverlay}
              onCommit={commitOverlay}
              locked={data.is_locked}
            />
          </div>
          <InlineError
            message={updateOverlay.error ? errorMessage(updateOverlay.error) : null}
            className="mt-2 text-xs text-destructive"
          />
        </section>
      </div>
    </div>
  );
}
