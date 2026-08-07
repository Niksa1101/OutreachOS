import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';

import { useMediaSrc } from '@/core/media/use-media-src';
import type { TalkingHeadDetail } from '@/core/api/types';
import { Slider } from '@/core/components/ui/slider';
import { useUpdateTalkingHeadTrim } from '@/modules/video-composer/api/campaigns';
import { formatDurationMs } from '@/modules/video-composer/lib/format-media';
import type { OverlayConfig } from '@/modules/video-composer/lib/overlay-geometry';
import { sliderValueAt } from '@/modules/video-composer/lib/slider-value';
import {
  clampFocalPoint,
  clampTrimWindow,
  resolvedDurationMs,
  type FocalPoint,
  type TrimWindow,
} from '@/modules/video-composer/lib/talking-head-trim';

interface Props {
  campaignId: string;
  talkingHead: TalkingHeadDetail;
  overlay: OverlayConfig;
  /** Ticket 21: trim and focal point are read-only while the campaign is locked. */
  locked?: boolean;
}

/**
 * The talking-head editor (ticket 13): a player scrubbing the same local
 * media the split-view preview background resolves through (`useMediaSrc`,
 * ticket 09), a trim timeline whose in/out handles can never invert, exceed
 * source bounds, or collapse to zero length, and a focal point draggable
 * inside a live approximation of the current overlay shape.
 *
 * Trim and focal point are edited together and persisted through one
 * request — the server re-clamps both regardless (mirrors
 * `update_overlay_config`'s "server is the actual source of truth" pattern) —
 * and any successful commit invalidates the campaign's alpha cache key
 * (`service._invalidate_alpha_cache`, same call `assign_talking_head` makes).
 */
export function TalkingHeadEditor({ campaignId, talkingHead, overlay, locked = false }: Props) {
  const resolvedSrc = useMediaSrc(talkingHead.file_missing ? null : talkingHead.source_path);
  const updateTrim = useUpdateTalkingHeadTrim();
  const durationMs = talkingHead.duration_ms;

  const [trim, setTrim] = useState<TrimWindow>({
    trim_start_ms: talkingHead.trim_start_ms,
    trim_end_ms: talkingHead.trim_end_ms,
  });
  const [focal, setFocal] = useState<FocalPoint>({
    focal_x: talkingHead.focal_x,
    focal_y: talkingHead.focal_y,
  });

  // Re-derive from the server only when the persisted values themselves
  // change — same pattern as `CampaignDetailScreen`'s overlay draft — so a
  // mid-drag handle or an unrelated campaign-detail refetch never clobbers
  // the other.
  useEffect(() => {
    setTrim({ trim_start_ms: talkingHead.trim_start_ms, trim_end_ms: talkingHead.trim_end_ms });
    setFocal({ focal_x: talkingHead.focal_x, focal_y: talkingHead.focal_y });
  }, [
    talkingHead.trim_start_ms,
    talkingHead.trim_end_ms,
    talkingHead.focal_x,
    talkingHead.focal_y,
  ]);

  function commit(nextTrim: TrimWindow, nextFocal: FocalPoint) {
    if (locked) return;
    updateTrim.mutate({
      campaignId,
      trim_start_ms: nextTrim.trim_start_ms,
      trim_end_ms: nextTrim.trim_end_ms,
      focal_x: nextFocal.focal_x,
      focal_y: nextFocal.focal_y,
    });
  }

  // --- player ---------------------------------------------------------

  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(trim.trim_start_ms);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    // Stop at trim-out so what plays back always matches what renders.
    const onTime = () => {
      const ms = video.currentTime * 1000;
      if (ms >= trim.trim_end_ms) {
        video.pause();
        video.currentTime = trim.trim_end_ms / 1000;
        setCurrentMs(trim.trim_end_ms);
      } else {
        setCurrentMs(ms);
      }
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    video.addEventListener('timeupdate', onTime);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    return () => {
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
    };
  }, [resolvedSrc.data, trim.trim_end_ms]);

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }

  function seekTo(ms: number) {
    setCurrentMs(ms);
    const video = videoRef.current;
    if (video) video.currentTime = ms / 1000;
  }

  // --- trim timeline ---------------------------------------------------

  function trimPairFrom(value: number | readonly number[]): [number, number] | null {
    if (!Array.isArray(value) || value.length < 2) return null;
    const start = sliderValueAt(value, 0);
    const end = sliderValueAt(value, 1);
    if (Number.isNaN(start) || Number.isNaN(end)) return null;
    return [start, end];
  }

  function handleTrimChange(value: number | readonly number[]) {
    const pair = trimPairFrom(value);
    if (!pair) return;
    const [start, end] = pair;
    const next = clampTrimWindow({ trim_start_ms: start, trim_end_ms: end }, durationMs);
    setTrim(next);
    // Keep the playhead inside the trimmed window while dragging a handle.
    if (currentMs < next.trim_start_ms) seekTo(next.trim_start_ms);
    else if (currentMs > next.trim_end_ms) seekTo(next.trim_end_ms);
  }

  function handleTrimCommit(value: number | readonly number[]) {
    const pair = trimPairFrom(value);
    if (!pair) return;
    const [start, end] = pair;
    const next = clampTrimWindow({ trim_start_ms: start, trim_end_ms: end }, durationMs);
    setTrim(next);
    commit(next, focal);
  }

  // --- focal point -------------------------------------------------------

  const shapeRef = useRef<HTMLDivElement>(null);
  const focalPreviewRef = useRef<HTMLVideoElement>(null);
  const [shapeScale, setShapeScale] = useState(0);
  const focalDrag = useRef<{ pointerId: number; latest: FocalPoint } | null>(null);

  // The focal-point preview always shows the trim-in frame — the same still
  // every render pass would composite against for a static-focal crop.
  useEffect(() => {
    const video = focalPreviewRef.current;
    if (video && video.readyState > 0) {
      video.currentTime = trim.trim_start_ms / 1000;
    }
  }, [trim.trim_start_ms]);

  useLayoutEffect(() => {
    const el = shapeRef.current;
    if (!el) return;
    setShapeScale(el.getBoundingClientRect().width / overlay.size.width);
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setShapeScale(width / overlay.size.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [overlay.size.width]);

  function focalFromPointer(event: React.PointerEvent<HTMLDivElement>): FocalPoint {
    const rect = shapeRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return focal;
    return clampFocalPoint({
      focal_x: (event.clientX - rect.left) / rect.width,
      focal_y: (event.clientY - rect.top) / rect.height,
    });
  }

  function beginFocalDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (locked) return;
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    const next = focalFromPointer(event);
    focalDrag.current = { pointerId: event.pointerId, latest: next };
    setFocal(next);
  }

  function moveFocalDrag(event: React.PointerEvent<HTMLDivElement>) {
    const drag = focalDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const next = focalFromPointer(event);
    drag.latest = next;
    setFocal(next);
  }

  function endFocalDrag(event: React.PointerEvent<HTMLDivElement>) {
    const drag = focalDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    focalDrag.current = null;
    commit(trim, drag.latest);
  }

  const shapeRadius =
    overlay.shape === 'circle'
      ? '50%'
      : overlay.shape === 'rounded_rect'
        ? `${overlay.border_radius * shapeScale}px`
        : '0';

  if (talkingHead.file_missing) {
    return (
      <section>
        <h2 className="text-sm font-semibold tracking-tight">Trim & focal point</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          The talking-head file is missing — relocate it above to edit trim and focal point.
        </p>
      </section>
    );
  }

  const resolvedDuration = resolvedDurationMs(trim);

  return (
    <section className="rounded-2xl border border-border p-5">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-sm font-semibold tracking-tight">Trim & focal point</h2>
        <p className="text-sm font-medium tabular-nums" role="status">
          Output duration: {formatDurationMs(resolvedDuration)}
        </p>
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-border bg-black">
        {resolvedSrc.data ? (
          <video
            ref={videoRef}
            src={resolvedSrc.data}
            className="aspect-video w-full"
            onLoadedMetadata={() => seekTo(trim.trim_start_ms)}
          />
        ) : (
          <div className="aspect-video w-full" />
        )}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={togglePlay}
          className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border text-foreground hover:bg-muted/60"
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? (
            <Pause aria-hidden className="size-4" />
          ) : (
            <Play aria-hidden className="size-4" />
          )}
        </button>
        <span className="text-xs tabular-nums text-muted-foreground">
          {formatDurationMs(currentMs)} / {formatDurationMs(durationMs)}
        </span>
      </div>

      <div className="mt-3">
        <Slider
          aria-label="Playhead"
          min={0}
          max={durationMs}
          step={1}
          value={[currentMs]}
          disabled={locked}
          onValueChange={(next) => seekTo(sliderValueAt(next, 0))}
        />
      </div>

      <div className="mt-4">
        <Slider
          aria-label="Trim window"
          min={0}
          max={durationMs}
          step={1}
          value={[trim.trim_start_ms, trim.trim_end_ms]}
          disabled={locked}
          onValueChange={handleTrimChange}
          onValueCommitted={handleTrimCommit}
        />
        <div className="mt-1.5 flex justify-between text-[11px] tabular-nums text-muted-foreground">
          <span>In {formatDurationMs(trim.trim_start_ms)}</span>
          <span>Out {formatDurationMs(trim.trim_end_ms)}</span>
        </div>
      </div>

      <div className="mt-5">
        <p className="text-xs font-medium text-muted-foreground">Focal point</p>
        <div
          ref={shapeRef}
          role="slider"
          aria-label="Focal point"
          aria-valuetext={`x ${focal.focal_x.toFixed(2)}, y ${focal.focal_y.toFixed(2)}`}
          aria-disabled={locked}
          tabIndex={locked ? -1 : 0}
          className={`relative mt-2 touch-none overflow-hidden border border-border bg-black select-none ${locked ? 'cursor-not-allowed opacity-60' : ''}`}
          style={{
            width: '100%',
            maxWidth: 280,
            aspectRatio: `${overlay.size.width} / ${overlay.size.height}`,
            borderRadius: shapeRadius,
          }}
          onPointerDown={beginFocalDrag}
          onPointerMove={moveFocalDrag}
          onPointerUp={endFocalDrag}
          onPointerCancel={endFocalDrag}
        >
          {resolvedSrc.data ? (
            <video
              ref={focalPreviewRef}
              src={resolvedSrc.data}
              muted
              playsInline
              aria-hidden
              className="pointer-events-none absolute inset-0 h-full w-full object-cover"
              style={{ objectPosition: `${focal.focal_x * 100}% ${focal.focal_y * 100}%` }}
              onLoadedMetadata={(event) => {
                event.currentTarget.currentTime = trim.trim_start_ms / 1000;
              }}
            />
          ) : null}
          <div
            className="pointer-events-none absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-primary shadow"
            style={{ left: `${focal.focal_x * 100}%`, top: `${focal.focal_y * 100}%` }}
          />
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Drag to set what stays centered when the talking head is cropped to fill the overlay.
        </p>
      </div>
    </section>
  );
}
