"""Per-video render pipeline."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from outreachos_backend.rendering.alpha import AlphaBuildResult
from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import temp_sibling
from outreachos_backend.rendering.capabilities import select_encoder
from outreachos_backend.rendering.config import RenderBatchConfig, ScreenRecordingJob
from outreachos_backend.rendering.errors import (
    WARN_ASPECT_RATIO_NOT_16_9,
    WARN_RECORDING_SHORTER_THAN_TALKING_HEAD,
    RenderError,
    RenderFatalError,
    RenderWarning,
)
from outreachos_backend.rendering.geometry import CANVAS_HEIGHT, CANVAS_WIDTH, OUTPUT_FPS
from outreachos_backend.rendering.pipeline import build_video_graph
from outreachos_backend.rendering.presets import audio_encode_args, video_encode_args
from outreachos_backend.rendering.probe import probe_media
from outreachos_backend.rendering.process import FfmpegProcess, run_tool
from outreachos_backend.rendering.progress import ProgressParser

__all__ = ["JobResult", "render_batch", "render_one"]

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, float], None]


@dataclass
class JobResult:
    output_path: Path | None
    ok: bool
    warnings: list[RenderWarning] = field(default_factory=list)
    error: str | None = None
    command: list[str] | None = None


def render_batch(
    binaries: Binaries,
    config: RenderBatchConfig,
    alpha: AlphaBuildResult,
    out_dir: Path,
    *,
    dry_run: bool = False,
    force_libx264: bool = False,
    deterministic: bool = False,
    on_progress: ProgressCallback | None = None,
) -> list[JobResult]:
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    encoder = select_encoder(binaries, config.encoder)
    results: list[JobResult] = []
    for job in config.recordings:
        result = render_one(
            binaries,
            config,
            alpha,
            job,
            out_dir,
            encoder=encoder,
            dry_run=dry_run,
            force_libx264=force_libx264,
            deterministic=deterministic,
            on_progress=on_progress,
        )
        results.append(result)
    return results


def render_one(
    binaries: Binaries,
    config: RenderBatchConfig,
    alpha: AlphaBuildResult,
    job: ScreenRecordingJob,
    out_dir: Path,
    *,
    encoder: str,
    dry_run: bool = False,
    force_libx264: bool = False,
    deterministic: bool = False,
    on_progress: ProgressCallback | None = None,
) -> JobResult:
    warnings: list[RenderWarning] = []
    source = job.source_path
    if not source.is_file():
        return JobResult(None, False, error=f"Source not found: {source}")

    try:
        probe = probe_media(binaries, str(source))
    except RenderError as exc:
        # An unreadable or truncated recording is that job's failure, not the
        # batch's: letting it propagate would drop every video queued behind it.
        return JobResult(None, False, error=str(exc))

    if probe.display_width != CANVAS_WIDTH or probe.display_height != CANVAS_HEIGHT:
        ratio = probe.display_width / max(1, probe.display_height)
        target = 16 / 9
        if abs(ratio - target) > 0.01:
            warnings.append(
                RenderWarning(
                    WARN_ASPECT_RATIO_NOT_16_9,
                    f"{source.name} is not 16:9 ({probe.display_width}x{probe.display_height})",
                )
            )

    trim_start = job.trim_start_ms / 1000.0
    rec_duration = (
        job.trim_end_ms / 1000.0 if job.trim_end_ms is not None else probe.duration_s
    ) - trim_start
    if rec_duration <= 0:
        # Reaching FFmpeg with a negative `-t` produces an opaque process error.
        return JobResult(
            None,
            False,
            warnings=warnings,
            error=(
                f"Trim window is empty: {source.name} runs {probe.duration_s:.3f}s "
                f"but trim starts at {trim_start:.3f}s"
            ),
        )
    if rec_duration + 0.001 < alpha.duration_s:
        warnings.append(
            RenderWarning(
                WARN_RECORDING_SHORTER_THAN_TALKING_HEAD,
                f"{source.name} shorter than talking-head duration; last frame frozen",
            )
        )

    target_frames = alpha.frame_count
    d_exact = target_frames / OUTPUT_FPS

    graph = build_video_graph(
        recording_input=str(source),
        alpha_input=str(alpha.clip_path),
        trim_start_s=trim_start,
        trim_duration_s=rec_duration,
        source_width=probe.display_width,
        source_height=probe.display_height,
        target_frames=target_frames,
        target_duration_s=d_exact,
        overlay_x=alpha.assets.geometry.overlay_x,
        overlay_y=alpha.assets.geometry.overlay_y,
    )

    out_path = out_dir / f"{job.output_basename}.mp4"
    part_path = temp_sibling(out_path, ".part.mp4")
    duration_us = int(d_exact * 1_000_000)

    command: list[str] = [
        str(binaries.ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-progress",
        "pipe:1",
        *graph.input_args,
        "-filter_complex",
        graph.filter_complex,
        "-map",
        f"[{graph.video_label}]",
        "-map",
        graph.audio_map,
        *video_encode_args(
            encoder,
            config.quality,
            force_libx264=force_libx264,
            deterministic=deterministic,
        ),
        *audio_encode_args(),
        "-fps_mode",
        "cfr",
        "-frames:v",
        str(target_frames),
        "-t",
        str(d_exact),
        "-movflags",
        "+faststart",
        "-y",
        str(part_path),
    ]

    if dry_run:
        log.info("dry-run render: %s", " ".join(command))
        return JobResult(out_path, True, warnings=warnings, command=command)

    out_dir.mkdir(parents=True, exist_ok=True)
    parser = ProgressParser(duration_us=duration_us)

    def progress_line(line: str) -> None:
        pct = parser.feed_line(line)
        if pct is not None and on_progress is not None:
            on_progress(job.output_basename, pct)

    proc = FfmpegProcess(command)
    try:
        proc.run(on_progress_line=progress_line)
        # Validate the part file, then rename. Committing first would leave a corrupt
        # MP4 at the output path for a job that reports failure.
        _assert_output_frames(binaries, part_path, target_frames)
    except RenderError as exc:
        part_path.unlink(missing_ok=True)
        return JobResult(
            None,
            False,
            warnings=warnings,
            error=_error_detail(exc),
            command=command,
        )

    part_path.replace(out_path)
    return JobResult(out_path, True, warnings=warnings, command=command)


def _error_detail(exc: RenderError) -> str:
    """FFmpeg's stderr is the part a user can act on; the message alone rarely is."""
    stderr = getattr(exc, "stderr", "")
    return f"{exc}\n{stderr}".rstrip() if stderr else str(exc)


def _assert_output_frames(binaries: Binaries, path: Path, expected: int) -> None:
    command = [
        str(binaries.ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_frames",
        "-of",
        "json",
        str(path),
    ]
    try:
        payload = json.loads(run_tool(command, timeout_s=60.0))
    except json.JSONDecodeError as exc:
        raise RenderFatalError(f"Unparseable ffprobe output for {path}: {exc}") from exc
    streams = payload.get("streams", [])
    if not streams:
        raise RenderFatalError(f"No video stream in output {path}")
    nb = streams[0].get("nb_frames")
    if nb in (None, "N/A"):
        probe = probe_media(binaries, str(path))
        actual = max(1, round(probe.duration_s * OUTPUT_FPS))
    else:
        actual = int(nb)
    if actual != expected:
        raise RenderFatalError(
            f"Output frame count mismatch for {path}: expected {expected}, got {actual}"
        )
