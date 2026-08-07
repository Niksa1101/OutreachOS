import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { errorMessage } from '@/core/api/error-message';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { InlineError } from '@/core/ui/InlineError';
import {
  presetsListQuery,
  useApplyPreset,
  useCreatePreset,
} from '@/modules/video-composer/api/campaigns';
import { ManagePresetsDialog } from '@/modules/video-composer/components/ManagePresetsDialog';
import {
  parseOverlayConfig,
  type OverlayConfig,
} from '@/modules/video-composer/lib/overlay-geometry';

interface Props {
  campaignId: string;
  overlay: OverlayConfig;
  onApplied: (overlay: OverlayConfig) => void;
  /** Ticket 21: applying a preset is blocked while the campaign is locked; saving one is not. */
  locked?: boolean;
}

/**
 * Ticket 14: Apply Preset, Save as Preset, and the Manage-presets entry
 * point, inline in the Overlay section. Presets are global (not scoped to
 * this campaign) and applying copies values rather than linking them.
 */
export function PresetControls({ campaignId, overlay, onApplied, locked = false }: Props) {
  const presets = useQuery(presetsListQuery);
  const applyPreset = useApplyPreset();
  const createPreset = useCreatePreset();

  const [selectedPresetId, setSelectedPresetId] = useState<string>('');
  const [applyError, setApplyError] = useState<string | null>(null);

  const [presetName, setPresetName] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);

  const [manageOpen, setManageOpen] = useState(false);

  function handleApply() {
    if (!selectedPresetId) return;
    setApplyError(null);
    applyPreset.mutate(
      { campaignId, preset_id: selectedPresetId },
      {
        onSuccess: (detail) => onApplied(parseOverlayConfig(detail.overlay_config)),
        onError: (error) => setApplyError(errorMessage(error)),
      },
    );
  }

  function handleSave() {
    const trimmed = presetName.trim();
    if (!trimmed) return;
    setSaveError(null);
    createPreset.mutate(
      { name: trimmed, overlay },
      { onSuccess: () => setPresetName(''), onError: (error) => setSaveError(errorMessage(error)) },
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <div>
        <p className="text-xs font-medium text-muted-foreground">Apply preset</p>
        <div className="mt-1.5 flex items-center gap-2">
          <Select
            value={selectedPresetId}
            disabled={locked}
            onValueChange={(value) => setSelectedPresetId(value ?? '')}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select a preset…" />
            </SelectTrigger>
            <SelectContent>
              {(presets.data?.presets ?? []).map((preset) => (
                <SelectItem key={preset.id} value={preset.id}>
                  {preset.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={locked || !selectedPresetId || applyPreset.isPending}
            onClick={handleApply}
          >
            Apply
          </Button>
        </div>
        <InlineError message={applyError} className="mt-1 text-xs text-destructive" />
      </div>

      <div>
        <p className="text-xs font-medium text-muted-foreground">Save as preset</p>
        <div className="mt-1.5 flex items-center gap-2">
          <Input
            value={presetName}
            maxLength={200}
            placeholder="Preset name"
            onChange={(event) => setPresetName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') handleSave();
            }}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!presetName.trim() || createPreset.isPending}
            onClick={handleSave}
          >
            Save
          </Button>
        </div>
        <InlineError message={saveError} className="mt-1 text-xs text-destructive" />
      </div>

      <Button type="button" variant="ghost" size="sm" onClick={() => setManageOpen(true)}>
        Manage presets
      </Button>
      <ManagePresetsDialog open={manageOpen} onOpenChange={setManageOpen} />
    </div>
  );
}
