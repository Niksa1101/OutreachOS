import { Link, useMatch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Play } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Skeleton } from '@/core/components/ui/skeleton';
import { campaignDetailQuery } from '@/modules/video-composer/api/campaigns';
import { CampaignPreviewPane } from '@/modules/video-composer/components/CampaignPreviewPane';
import { RecordingImportPanel } from '@/modules/video-composer/components/RecordingImportPanel';
import { RecordingsTable } from '@/modules/video-composer/components/RecordingsTable';
import { TalkingHeadPanel } from '@/modules/video-composer/components/TalkingHeadPanel';
import { ValidationSummary } from '@/modules/video-composer/components/ValidationSummary';

export function CampaignDetailScreen() {
  const { campaignId } = useMatch({ strict: false }).params as { campaignId: string };
  const { data, isPending, isError } = useQuery(campaignDetailQuery(campaignId));

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

        <div className="mt-4">
          <ValidationSummary validation={data.validation} />
        </div>

        <div className="mt-6 space-y-6">
          <TalkingHeadPanel campaignId={data.id} talkingHead={data.talking_head ?? null} />
          <RecordingImportPanel campaignId={data.id} />
          <RecordingsTable
            campaignId={data.id}
            recordings={data.recordings ?? []}
            validationIssues={data.validation.issues ?? []}
          />
        </div>
      </div>

      {/* `self-start`: without it the grid stretches this column to match the
          left column's height, leaving no room for `sticky` to have any
          scrolling left to pin against. */}
      <div className="lg:sticky lg:top-6 lg:self-start">
        <CampaignPreviewPane campaignId={data.id} />
      </div>
    </div>
  );
}
