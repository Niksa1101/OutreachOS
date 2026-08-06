import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

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
import { Skeleton } from '@/core/components/ui/skeleton';
import { InlineError } from '@/core/ui/InlineError';
import {
  campaignDeletePreviewQuery,
  useDeleteCampaign,
} from '@/modules/video-composer/api/campaigns';
import {
  describeAlphaClip,
  describeCampaignData,
  describeOutputs,
} from '@/modules/video-composer/lib/delete-preview';

interface Props {
  campaignId: string | null;
  campaignName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeleteCampaignDialog({ campaignId, campaignName, open, onOpenChange }: Props) {
  const deleteCampaign = useDeleteCampaign();
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const preview = useQuery({
    ...campaignDeletePreviewQuery(campaignId ?? ''),
    enabled: open && campaignId !== null,
  });

  const handleConfirm = () => {
    if (!campaignId) return;

    deleteCampaign.mutate(campaignId, {
      onSuccess: () => onOpenChange(false),
      onError: (error) => setDeleteError(errorMessage(error)),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{campaignName}”?</AlertDialogTitle>
          <AlertDialogDescription>
            This removes the following from your workspace. Your source recordings on disk are never
            touched.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {preview.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/6" />
          </div>
        ) : preview.isError ? (
          <p className="text-sm text-destructive">
            Could not load what would be removed. Try again in a moment.
          </p>
        ) : preview.data ? (
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-foreground">
            <li>
              {describeCampaignData(
                preview.data.asset_count,
                preview.data.recording_count,
                preview.data.talking_head_count,
              )}
            </li>
            <li>
              {describeAlphaClip(
                preview.data.alpha_clip.present,
                preview.data.alpha_clip.size_bytes,
              )}
            </li>
            <li>
              {describeOutputs(preview.data.outputs.count, preview.data.outputs.total_size_bytes)}
            </li>
          </ul>
        ) : null}

        <InlineError message={deleteError} className="text-sm text-destructive" />

        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteCampaign.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={preview.isPending || preview.isError || deleteCampaign.isPending}
            onClick={handleConfirm}
          >
            Delete campaign
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
