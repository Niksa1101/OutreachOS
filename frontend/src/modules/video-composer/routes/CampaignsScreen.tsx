import { useQuery } from '@tanstack/react-query';
import { LayoutList, Plus } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Skeleton } from '@/core/components/ui/skeleton';
import { EmptyState } from '@/core/ui/EmptyState';
import { campaignsListQuery, useCreateCampaign } from '@/modules/video-composer/api/campaigns';
import { CampaignsTable } from '@/modules/video-composer/components/CampaignsTable';

export function CampaignsScreen() {
  const { data, isPending, isError } = useQuery(campaignsListQuery);
  const createCampaign = useCreateCampaign();

  const handleCreate = () => {
    createCampaign.mutate({});
  };

  if (isPending) {
    return (
      <div className="p-6">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="mt-6 h-48 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-semibold tracking-tight">Campaigns</h1>
        <p className="mt-4 text-sm text-muted-foreground">
          Could not load campaigns. Check that the backend is running.
        </p>
      </div>
    );
  }

  const campaigns = data.campaigns;

  if (campaigns.length === 0) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-semibold tracking-tight">Campaigns</h1>
        <EmptyState
          icon={LayoutList}
          title="No campaigns yet"
          description="A campaign holds one talking-head recording and the screen recordings it is composited onto. Create one to get started."
          action={
            <Button onClick={handleCreate} disabled={createCampaign.isPending} size="sm">
              Create campaign
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-lg font-semibold tracking-tight">Campaigns</h1>
        <Button
          onClick={handleCreate}
          disabled={createCampaign.isPending}
          size="sm"
          data-icon="inline-start"
        >
          <Plus aria-hidden />
          Create campaign
        </Button>
      </div>
      <CampaignsTable campaigns={campaigns} />
    </div>
  );
}
