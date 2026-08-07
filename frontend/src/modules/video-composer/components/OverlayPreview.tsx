import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import {
  computeInnerOverlayBox,
  computeOverlayBox,
  DEFAULT_CANVAS,
  dragOverlayBy,
  resizeOverlayBy,
  type Anchor,
  type OverlayConfig,
} from '@/modules/video-composer/lib/overlay-geometry';

/**
 * `resizeOverlayBy` pins the anchor's own corner and grows/shrinks from the
 * diagonally opposite one — the handle must render at that free corner (and
 * carry the matching resize cursor) or dragging it moves the box away from
 * the cursor instead of with it (finding D1).
 */
const RESIZE_HANDLE_BY_ANCHOR: Record<Anchor, { position: string; cursor: string }> = {
  top_left: { position: '-right-1.5 -bottom-1.5', cursor: 'cursor-nwse-resize' },
  top_right: { position: '-left-1.5 -bottom-1.5', cursor: 'cursor-nesw-resize' },
  bottom_left: { position: '-right-1.5 -top-1.5', cursor: 'cursor-nesw-resize' },
  bottom_right: { position: '-left-1.5 -top-1.5', cursor: 'cursor-nwse-resize' },
};

interface Props {
  overlay: OverlayConfig;
  /** Fired continuously while dragging/resizing, for live-synced numeric fields. */
  onChange: (overlay: OverlayConfig) => void;
  /** Fired once the pointer is released — the point at which the result should persist. */
  onCommit: (overlay: OverlayConfig) => void;
  /** Ticket 21: dragging/resizing is disabled while the campaign is locked. */
  locked?: boolean;
}

/**
 * Calibrated CSS approximation of the render engine's overlay compositing
 * (ticket 10), made directly manipulable (ticket 11) — drag to reposition,
 * the handle to resize, both with magnetic snap near corners/safe margin.
 * `overlay_assets.py` (Pillow) remains the source of truth for the rendered
 * output; the shadow's CSS `blur` mapping in particular is a first-pass guess
 * pending visual comparison against a real render (PRD Known Risk #2).
 *
 * Position/size are plain CSS percentages against the parent canvas box, so
 * they track the border-box's rendered size automatically. Border width and
 * shadow blur/offset are logical canvas pixels that must be scaled to the
 * canvas's current on-screen size — hence the `ResizeObserver`. Drag/resize
 * deltas are measured in *screen* pixels and divided by that same scale
 * before being handed to the pure geometry functions, so a slow zoom or a
 * narrow window never changes how far the overlay moves per pixel dragged.
 */
export function OverlayPreview({ overlay, onChange, onCommit, locked = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);
  const [faded, setFaded] = useState(false);
  const dragState = useRef<{
    kind: 'move' | 'resize';
    pointerId: number;
    startClientX: number;
    startClientY: number;
    startOverlay: OverlayConfig;
    latest: OverlayConfig;
  } | null>(null);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // `ResizeObserver`'s first callback is asynchronous, which would leave
    // border/shadow at scale 0 for a frame; measure synchronously up front
    // so the initial paint is already correct, then let the observer take
    // over for later resizes.
    setScale(el.getBoundingClientRect().width / DEFAULT_CANVAS.width);
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setScale(width / DEFAULT_CANVAS.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Non-frame-accurate fade preview: opacity transitions from 0 to
  // `overlay.opacity` over `animation.duration_ms` on mount, driven by CSS
  // rather than the render engine's per-frame alpha ramp. Re-runs whenever
  // `duration_ms` changes so editing that field is actually previewable.
  useEffect(() => {
    setFaded(false);
    const id = requestAnimationFrame(() => setFaded(true));
    return () => cancelAnimationFrame(id);
  }, [overlay.animation.duration_ms]);

  const box = computeOverlayBox(overlay);
  const inner = computeInnerOverlayBox(overlay);
  const px = (logical: number) => logical * scale;

  const leftPct = (box.x / DEFAULT_CANVAS.width) * 100;
  const topPct = (box.y / DEFAULT_CANVAS.height) * 100;
  const widthPct = (box.width / DEFAULT_CANVAS.width) * 100;
  const heightPct = (box.height / DEFAULT_CANVAS.height) * 100;

  const radius =
    overlay.shape === 'circle'
      ? '50%'
      : overlay.shape === 'rounded_rect'
        ? `${px(overlay.border_radius)}px`
        : '0';
  const innerRadius =
    overlay.shape === 'circle'
      ? '50%'
      : overlay.shape === 'rounded_rect'
        ? `${px(Math.max(overlay.border_radius - inner.padding, 0))}px`
        : '0';

  const boxShadow = overlay.shadow.enabled
    ? `${px(overlay.shadow.offset_x)}px ${px(overlay.shadow.offset_y)}px ${px(overlay.shadow.blur)}px ${hexToRgba(overlay.shadow.color, overlay.shadow.opacity)}`
    : 'none';

  const positionStyle = {
    left: `${leftPct}%`,
    top: `${topPct}%`,
    width: `${widthPct}%`,
    height: `${heightPct}%`,
    borderRadius: radius,
  };

  function beginDrag(kind: 'move' | 'resize') {
    return (event: React.PointerEvent<HTMLDivElement>) => {
      if (locked) return;
      event.preventDefault();
      event.stopPropagation();
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      dragState.current = {
        kind,
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startOverlay: overlay,
        latest: overlay,
      };
    };
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId || scale === 0) return;
    const deltaX = (event.clientX - drag.startClientX) / scale;
    const deltaY = (event.clientY - drag.startClientY) / scale;
    const next =
      drag.kind === 'move'
        ? dragOverlayBy(drag.startOverlay, deltaX, deltaY)
        : resizeOverlayBy(drag.startOverlay, deltaX, deltaY);
    drag.latest = next;
    onChange(next);
  }

  function endDrag(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragState.current = null;
    onCommit(drag.latest);
  }

  return (
    <div ref={containerRef} className="absolute inset-0">
      {overlay.background.enabled ? (
        <div
          className="pointer-events-none absolute"
          style={{ ...positionStyle, backgroundColor: overlay.background.color }}
        />
      ) : null}
      <div
        role="slider"
        aria-label="Overlay position"
        aria-valuetext={`x ${overlay.offset.x}, y ${overlay.offset.y}`}
        aria-disabled={locked}
        tabIndex={locked ? -1 : 0}
        className={`absolute touch-none select-none ${locked ? 'cursor-not-allowed' : 'cursor-grab active:cursor-grabbing'}`}
        style={{
          ...positionStyle,
          border: overlay.border.enabled
            ? `${px(overlay.border.width)}px solid ${overlay.border.color}`
            : undefined,
          boxShadow,
        }}
        onPointerDown={beginDrag('move')}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div
          className="pointer-events-none absolute flex items-center justify-center overflow-hidden bg-white/20 text-[10px] font-medium text-white/70"
          style={{
            inset: `${px(inner.padding)}px`,
            borderRadius: innerRadius,
            opacity: faded ? overlay.opacity : 0,
            transition: `opacity ${overlay.animation.duration_ms}ms ease`,
          }}
        >
          Talking head
        </div>
        <div
          role="slider"
          aria-label="Resize overlay"
          aria-valuetext={`${box.width}×${box.height}`}
          aria-disabled={locked}
          tabIndex={locked ? -1 : 0}
          className={`absolute size-3.5 touch-none rounded-full border-2 border-white bg-primary shadow ${RESIZE_HANDLE_BY_ANCHOR[overlay.anchor].position} ${locked ? 'cursor-not-allowed' : RESIZE_HANDLE_BY_ANCHOR[overlay.anchor].cursor}`}
          onPointerDown={beginDrag('resize')}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        />
      </div>
    </div>
  );
}

function hexToRgba(hex: string, alpha: number): string {
  const value = hex.replace('#', '');
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
