"""Alpha clip builder with cache integration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import (
    AlphaManifest,
    CacheLayout,
    alpha_cache_key,
    alpha_clip_path,
    alpha_manifest_path,
    assets_cache_key,
    atomic_write_text,
    probe_alpha_cache_hit,
    temp_sibling,
)
from outreachos_backend.rendering.config import OverlayConfig, RenderBatchConfig
from outreachos_backend.rendering.errors import RenderFatalError
from outreachos_backend.rendering.geometry import OUTPUT_FPS, compute_geometry, quantize_duration
from outreachos_backend.rendering.overlay_assets import (
    OverlayAssets,
    asset_paths_for,
    render_overlay_assets,
)
from outreachos_backend.rendering.pipeline import build_alpha_graph
from outreachos_backend.rendering.probe import ProbeResult, probe_media
from outreachos_backend.rendering.process import FfmpegProcess

__all__ = ["AlphaBuildResult", "build_alpha_clip", "ensure_overlay_assets"]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlphaBuildResult:
    alpha_key: str
    assets_key: str
    clip_path: Path
    frame_count: int
    duration_s: float
    cache_hit: bool
    assets: OverlayAssets


def ensure_overlay_assets(
    overlay: OverlayConfig,
    layout: CacheLayout,
) -> tuple[str, OverlayAssets]:
    geometry = compute_geometry(overlay)
    key = assets_cache_key(overlay, geometry)
    backdrop, mask, frame = asset_paths_for(layout.assets_dir, key)
    if backdrop.is_file() and mask.is_file() and frame.is_file():
        return key, OverlayAssets(
            backdrop=backdrop,
            mask=mask,
            frame=frame,
            geometry=geometry,
        )
    layout.assets_dir.mkdir(parents=True, exist_ok=True)
    assets = render_overlay_assets(overlay, layout.assets_dir, assets_key=key)
    return key, assets


def build_alpha_clip(
    binaries: Binaries,
    config: RenderBatchConfig,
    layout: CacheLayout,
    *,
    dry_run: bool = False,
    job_id: str | None = None,
) -> AlphaBuildResult:
    talking = config.talking_head
    if not talking.source_path.is_file():
        raise RenderFatalError(f"Talking head not found: {talking.source_path}")

    assets_key, assets = ensure_overlay_assets(config.overlay, layout)
    alpha_key = alpha_cache_key(talking, config.overlay, assets_key)
    clip = alpha_clip_path(layout, alpha_key)

    cached = probe_alpha_cache_hit(binaries, clip)
    if cached is not None:
        frames = cached.nb_frames or _frame_count_from_duration(cached.duration_s)
        return AlphaBuildResult(
            alpha_key=alpha_key,
            assets_key=assets_key,
            clip_path=clip,
            frame_count=frames,
            duration_s=cached.duration_s,
            cache_hit=True,
            assets=assets,
        )

    head_probe = probe_media(binaries, str(talking.source_path))
    trim_start = talking.trim_start_ms / 1000.0
    trim_end = (
        talking.trim_end_ms / 1000.0 if talking.trim_end_ms is not None else head_probe.duration_s
    )
    # TrimmableSource guarantees trim_end > trim_start, so the only way to get here
    # non-positive is a source whose probed duration precedes the trim start.
    duration_s = trim_end - trim_start
    if duration_s <= 0:
        raise RenderFatalError(
            f"Talking head trim window is empty: {talking.source_path} runs "
            f"{head_probe.duration_s:.3f}s but trim starts at {trim_start:.3f}s"
        )
    frame_count, d_exact = quantize_duration(duration_s, OUTPUT_FPS)
    # Ticket 12: the configured duration is applied in full to *each* edge (not
    # split between them) — `AlphaFadeStep` clamps to `total_frames // 2` to keep
    # the two fades from overlapping on a clip too short to fit both.
    # A configured duration of 0 means no fade — `AlphaFadeStep` already
    # no-ops at `fade_frames <= 0`, so this isn't floored to 1.
    fade_frames = max(
        0,
        round(config.overlay.animation.duration_ms / 1000.0 * OUTPUT_FPS),
    )

    graph = build_alpha_graph(
        talking_head_input=str(talking.source_path),
        backdrop_input=str(assets.backdrop),
        mask_input=str(assets.mask),
        frame_input=str(assets.frame),
        trim_start_s=trim_start,
        duration_s=d_exact,
        has_audio=head_probe.has_audio,
        box_width=assets.geometry.box_width,
        box_height=assets.geometry.box_height,
        inner_width=assets.geometry.inner_width,
        inner_height=assets.geometry.inner_height,
        padding=assets.geometry.padding,
        bleed_width=assets.geometry.bleed_width,
        bleed_height=assets.geometry.bleed_height,
        inset_left=assets.geometry.bleed_insets.left,
        inset_top=assets.geometry.bleed_insets.top,
        focal_x=talking.focal_x,
        focal_y=talking.focal_y,
        fade_frames=fade_frames,
        total_frames=frame_count,
    )

    layout.alpha_dir.mkdir(parents=True, exist_ok=True)
    out_tmp = temp_sibling(clip, ".mov")
    audio_filter = _audio_filter(head_probe, frame_count)

    command: list[str] = [
        str(binaries.ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        # Pinning the encoder alone is not enough: overlay's framesync pairs its two
        # inputs nondeterministically when the filter graph runs across threads, so the
        # decoded frames differ run to run even though the encode is reproducible.
        # These are global options and must precede -filter_complex (ADR-0009).
        "-filter_threads",
        "1",
        "-filter_complex_threads",
        "1",
        *graph.input_args,
        "-filter_complex",
        graph.filter_complex,
        "-map",
        f"[{graph.video_label}]",
        "-map",
        graph.audio_map,
    ]
    if head_probe.has_audio:
        command.extend(["-af", audio_filter])

    command.extend(
        [
            "-fps_mode",
            "cfr",
            "-r",
            str(OUTPUT_FPS),
            "-frames:v",
            str(frame_count),
            "-t",
            str(d_exact),
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            # The alpha clip is a content-addressed cache entry, so the same key must
            # yield the same bytes: prores_ks slices work across threads by default and
            # produces a different file each run. The clip is small and built once per
            # batch, so pinning costs nothing measurable. Bitexact drops the encoder
            # version string and creation time from the container (ADR-0009).
            "-threads",
            "1",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-y",
            str(out_tmp),
        ]
    )

    if dry_run:
        log.info("dry-run alpha: %s", " ".join(command))
        return AlphaBuildResult(
            alpha_key=alpha_key,
            assets_key=assets_key,
            clip_path=clip,
            frame_count=frame_count,
            duration_s=d_exact,
            cache_hit=False,
            assets=assets,
        )

    proc = FfmpegProcess(command)
    try:
        proc.run(job_id=job_id)
        # Validate before the rename, never after. `is_alpha_cache_hit` accepts any
        # clip that probes, so a short clip committed here would be silently reused
        # on every later run — the first run fails loudly, the rest render at the
        # wrong duration.
        _assert_frame_count(binaries, out_tmp, frame_count)
    except BaseException:
        out_tmp.unlink(missing_ok=True)
        raise

    out_tmp.replace(clip)

    manifest = AlphaManifest(
        owner_ref=config.owner_ref,
        owner_kind=config.owner_kind,
        alpha_key=alpha_key,
        assets_key=assets_key,
    )
    atomic_write_text(
        alpha_manifest_path(layout, alpha_key),
        json.dumps(manifest.__dict__, sort_keys=True),
    )

    return AlphaBuildResult(
        alpha_key=alpha_key,
        assets_key=assets_key,
        clip_path=clip,
        frame_count=frame_count,
        duration_s=d_exact,
        cache_hit=False,
        assets=assets,
    )


def _audio_filter(probe: ProbeResult, frame_count: int) -> str:
    duration_s = frame_count / OUTPUT_FPS
    declick = f"afade=t=in:st=0:d=0.015,afade=t=out:st={max(0, duration_s - 0.015):f}:d=0.015"
    if probe.audio_sample_rate != 48000 or probe.audio_channels != 2:
        return f"aresample=48000,aformat=channel_layouts=stereo,{declick}"
    return declick


def _assert_frame_count(binaries: Binaries, clip: Path, expected: int) -> None:
    probe = probe_media(binaries, str(clip))
    actual = probe.nb_frames or _frame_count_from_duration(probe.duration_s)
    if actual != expected:
        raise RenderFatalError(
            f"Alpha clip frame count mismatch: expected {expected}, got {actual} ({clip})"
        )


def _frame_count_from_duration(duration_s: float) -> int:
    return max(1, round(duration_s * OUTPUT_FPS))
