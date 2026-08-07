import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/core/api/client';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import type { CampaignDetail, CampaignQualityUpdateRequest } from '@/core/api/types';
import { InlineError } from '@/core/ui/InlineError';

import { campaignQueryKeys } from '@/modules/video-composer/api/campaigns';

type QualityOverrideValue = 'inherit' | 'draft' | 'standard' | 'high';

const QUALITY_PRESET_LABELS: Record<'draft' | 'standard' | 'high', string> = {
  draft: 'Draft',
  standard: 'Standard',
  high: 'High',
};

function qualityOverrideToApi(value: QualityOverrideValue): CampaignQualityUpdateRequest {
  return {
    quality_override: value === 'inherit' ? null : value,
  };
}

function qualityOverrideFromApi(
  qualityOverride: CampaignDetail['quality_override'],
): QualityOverrideValue {
  if (qualityOverride === 'draft' || qualityOverride === 'standard' || qualityOverride === 'high') {
    return qualityOverride;
  }
  return 'inherit';
}

function useUpdateCampaignQuality(campaignId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CampaignQualityUpdateRequest) =>
      apiFetch<CampaignDetail>(`/campaigns/${campaignId}/quality`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(campaignQueryKeys.detail(campaignId), data);
    },
  });
}

interface Props {
  campaignId: string;
  qualityOverride: CampaignDetail['quality_override'];
  locked?: boolean;
}

/** Tri-state quality control: inherit global preset, or an explicit tier. */
export function QualityOverrideControl({ campaignId, qualityOverride, locked = false }: Props) {
  const updateQuality = useUpdateCampaignQuality(campaignId);
  const value = qualityOverrideFromApi(qualityOverride);

  return (
    <section>
      <h2 className="text-sm font-semibold tracking-tight">Render quality</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Override the global quality preset from Settings for this campaign only.
      </p>
      <div className="mt-3 max-w-xs">
        <Select
          value={value}
          disabled={locked || updateQuality.isPending}
          onValueChange={(next) => {
            if (
              next !== 'inherit' &&
              next !== 'draft' &&
              next !== 'standard' &&
              next !== 'high'
            ) {
              return;
            }
            updateQuality.mutate(qualityOverrideToApi(next));
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="inherit">Inherit global preset</SelectItem>
            <SelectItem value="draft">{QUALITY_PRESET_LABELS.draft}</SelectItem>
            <SelectItem value="standard">{QUALITY_PRESET_LABELS.standard}</SelectItem>
            <SelectItem value="high">{QUALITY_PRESET_LABELS.high}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <InlineError
        message={updateQuality.error ? updateQuality.error.message : null}
        className="mt-2 text-xs text-destructive"
      />
    </section>
  );
}
