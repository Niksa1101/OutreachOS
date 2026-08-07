import { ImageOff } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { useMediaSrc } from '@/core/media/use-media-src';
import { campaignPreviewFrameQuery } from '@/modules/video-composer/api/campaigns';
import { OverlayPreview } from '@/modules/video-composer/components/OverlayPreview';
import type { OverlayConfig } from '@/modules/video-composer/lib/overlay-geometry';

interface Props {
  campaignId: string;
  overlay: OverlayConfig;
  onOverlayChange: (overlay: OverlayConfig) => void;
  onOverlayCommit: (overlay: OverlayConfig) => void;
  /** Ticket 21: read-only while the campaign has queued/active render jobs. */
  locked?: boolean;
}

/**
 * The split-view preview's background (ticket 09).
 *
 * `aspect-[1920/1080]` is not a stylistic 16:9 — it is the render engine's
 * fixed output frame (`rendering/geometry.py` `CANVAS_WIDTH`/`CANVAS_HEIGHT`),
 * scaled to fit this box. `object-contain` mirrors `ScalePadStep`'s own
 * `force_original_aspect_ratio=decrease` + letterbox pad, so a coordinate
 * measured in the preview lands on the same output pixel a render would
 * produce — the thing later tickets that draw over this box depend on.
 */
export function CampaignPreviewPane({
  campaignId,
  overlay,
  onOverlayChange,
  onOverlayCommit,
  locked = false,
}: Props) {
  const { data, isPending } = useQuery(campaignPreviewFrameQuery(campaignId));
  const framePath = data?.available ? (data.frame_path ?? null) : null;
  const resolvedSrc = useMediaSrc(framePath);

  const showImage = framePath != null && resolvedSrc.data != null;
  const message = data && !data.available ? data.error : null;

  return (
    <section>
      <h2 className="text-sm font-semibold tracking-tight">Preview</h2>
      <div className="relative mt-3 flex aspect-[1920/1080] w-full items-center justify-center overflow-hidden rounded-2xl border border-border bg-black">
        {showImage ? (
          <img
            src={resolvedSrc.data}
            alt="Preview of the first screen recording"
            className="h-full w-full object-contain"
          />
        ) : isPending ? null : (
          <div className="flex flex-col items-center gap-2 px-6 text-center text-sm text-muted-foreground">
            <ImageOff aria-hidden className="size-6 opacity-60" />
            <p>{message ?? 'No recordings yet. Add one to see a preview here.'}</p>
          </div>
        )}
        <OverlayPreview
          overlay={overlay}
          onChange={onOverlayChange}
          onCommit={onOverlayCommit}
          locked={locked}
        />
      </div>
    </section>
  );
}
